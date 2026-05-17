"""
Unit tests for algo_position_sizer - Kelly Criterion position sizing.

Tests cover:
- Position sizing based on win/loss ratio and probability
- Risk-per-trade constraints (max 2% portfolio)
- Maximum position size constraints
- Correlation-adjusted sizing (reduce on high correlation)
- Cash availability validation
- Edge cases (kelly > 100%, zero probability, negative returns)

Critical for production: Correct sizing prevents catastrophic losses.
Bad sizing with high leverage = account blowup.
"""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from algo.algo_position_sizer import PositionSizer


class TestPositionSizing:
    """Test position sizing calculations."""

    @pytest.fixture
    def sizer(self):
        """Create position sizer for testing."""
        sizer = PositionSizer(
            portfolio_value=100000,
            max_position_pct=5.0,
            max_risk_pct=2.0,
            min_position_size=100,
            max_position_size=10000
        )
        return sizer

    # ========================================================================
    # Kelly Criterion Sizing
    # ========================================================================

    def test_kelly_sizing_basic(self, sizer):
        """Should calculate Kelly Criterion position size correctly."""
        # Win rate 60%, win size 2%, loss size 1%
        # Kelly = (0.6 * 2 - 0.4 * 1) / 2 = 0.5 = 50% of portfolio
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,  # 2% profit
            loss_payoff_pct=0.01   # 1% loss (risk/reward 1:2)
        )

        assert result['kelly_pct'] > 0
        assert result['kelly_pct'] <= 1.0
        assert result['position_size'] > 0

    def test_kelly_sizing_conservative_on_low_probability(self, sizer):
        """Should reduce sizing on lower win probabilities."""
        # 50% win rate
        result_50 = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.50,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        # 40% win rate
        result_40 = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.40,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        # Lower win probability should give smaller position
        assert result_50['position_size'] > result_40['position_size']

    def test_kelly_sizing_increases_on_better_risk_reward(self, sizer):
        """Should increase sizing with better risk/reward ratios."""
        # Risk/reward 1:2
        result_rr2 = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.55,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        # Risk/reward 1:4
        result_rr4 = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=148.00,
            target_price=162.00,
            win_probability=0.55,
            win_payoff_pct=0.04,
            loss_payoff_pct=0.02
        )

        # Better risk/reward should give larger position
        assert result_rr4['position_size'] > result_rr2['position_size']

    # ========================================================================
    # Risk Management Constraints
    # ========================================================================

    def test_max_risk_per_trade_constraint(self, sizer):
        """Should never risk more than max_risk_pct per trade."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=100.00,  # 50 point stop = 33% risk
            target_price=200.00,
            win_probability=0.60,
            win_payoff_pct=0.33,
            loss_payoff_pct=0.33
        )

        # Risk should be capped at 2%
        actual_risk_pct = (result['position_size'] * (150 - 100)) / sizer.portfolio_value
        assert actual_risk_pct <= sizer.max_risk_pct * 1.01  # Allow 1% floating point error

    def test_max_position_size_constraint(self, sizer):
        """Should never exceed max_position_size."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.99,
            win_payoff_pct=0.50,  # Extremely profitable
            loss_payoff_pct=0.01
        )

        assert result['position_size'] <= sizer.max_position_size

    def test_max_position_pct_constraint(self, sizer):
        """Should never exceed max_position_pct of portfolio."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.99,
            win_payoff_pct=0.50,
            loss_payoff_pct=0.01
        )

        position_value = result['position_size'] * 150.00
        position_pct = (position_value / sizer.portfolio_value) * 100
        assert position_pct <= sizer.max_position_pct * 1.01

    # ========================================================================
    # Correlation Adjustment
    # ========================================================================

    def test_reduce_sizing_on_high_correlation(self, sizer):
        """Should reduce position size when correlated to existing positions."""
        base_size = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        # Same trade but with 0.90 correlation to existing position
        correlated_size = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            correlation_to_existing=0.90
        )

        # High correlation should reduce position size
        assert correlated_size['position_size'] < base_size['position_size']

    def test_correlation_below_0_5_has_minimal_impact(self, sizer):
        """Should have minimal size reduction on low correlation (<0.5)."""
        low_corr_size = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            correlation_to_existing=0.20
        )

        uncorrelated_size = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            correlation_to_existing=0.0
        )

        # Low correlation should have minimal impact
        reduction_pct = (uncorrelated_size['position_size'] - low_corr_size['position_size']) / uncorrelated_size['position_size']
        assert reduction_pct < 0.1  # Less than 10% reduction

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_sizing_kelly_exceeds_100_pct(self, sizer):
        """Should cap Kelly fraction to practical maximum (usually 25%)."""
        # Extremely favorable trade (99% win rate, 1:1 risk/reward)
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=148.00,
            target_price=152.00,
            win_probability=0.99,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.02
        )

        position_value = result['position_size'] * 150.00
        position_pct = (position_value / sizer.portfolio_value) * 100
        assert position_pct <= 25.0  # Practical Kelly fraction cap

    def test_sizing_zero_probability(self, sizer):
        """Should handle zero probability gracefully."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.0,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        assert result['position_size'] == 0
        assert result['kelly_pct'] == 0

    def test_sizing_negative_expected_value(self, sizer):
        """Should not size positions with negative expected value."""
        # Losing trade (40% win, 1:2 risk/reward = -20% EV)
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.40,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01
        )

        assert result['position_size'] == 0
        assert result['kelly_pct'] <= 0

    def test_sizing_with_insufficient_cash(self, sizer):
        """Should return zero size if insufficient cash available."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            available_cash=500  # Not enough for even 1 share @ $150
        )

        assert result['position_size'] == 0


class TestMultiplePositionSizing:
    """Test sizing with multiple open positions."""

    @pytest.fixture
    def sizer(self):
        """Create position sizer for testing."""
        sizer = PositionSizer(
            portfolio_value=100000,
            max_position_pct=5.0,
            max_risk_pct=2.0,
            min_position_size=100,
            max_position_size=10000
        )
        return sizer

    def test_reduce_sizing_when_max_risk_exceeded(self, sizer):
        """Should reduce sizing if adding new position would exceed max portfolio risk."""
        # Suppose 1% is already at risk in existing positions
        new_size = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            existing_risk_pct=0.01  # 1% already at risk
        )

        # New position can risk at most 1% more (max is 2%)
        new_position_risk = (new_size['position_size'] * (150 - 145)) / sizer.portfolio_value
        assert (new_position_risk + 0.01) <= 0.02 * 1.01

    def test_zero_sizing_when_all_risk_allocated(self, sizer):
        """Should return zero size if max portfolio risk already allocated."""
        result = sizer.calculate_kelly_size(
            portfolio_value=100000,
            entry_price=150.00,
            stop_price=145.00,
            target_price=160.00,
            win_probability=0.60,
            win_payoff_pct=0.02,
            loss_payoff_pct=0.01,
            existing_risk_pct=0.02  # Already at max
        )

        assert result['position_size'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
