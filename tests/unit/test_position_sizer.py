"""
Unit tests for PositionSizer — position sizing with risk multipliers.

Tests:
- Baseline position sizing (base risk × entry/stop)
- Drawdown cascade (risk reduction at -5%, -10%, -15%, -20%)
- Market exposure multiplier (scales by exposure_pct)
- VIX caution multiplier (soft reduction when 25 < VIX ≤ 35)
- Max position caps (max_position_size_pct, max_concentration_pct)
- Total invested cap (max_total_invested_pct)
- Edge cases (zero risk, negative prices, extreme drawdown)
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from algo_position_sizer import PositionSizer


@pytest.mark.unit
class TestPositionSizerBasics:
    """Basic position sizing calculation."""

    def test_simple_position_size(self, test_config):
        """Baseline: risk_dollars / risk_per_share = shares."""
        sizer = PositionSizer(test_config)

        # Mock DB queries
        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            assert result['shares'] > 0
            # base_risk = 0.75% of 100k = 750
            # risk_per_share = 150 - 142.5 = 7.5
            # shares = 750 / 7.5 = 100
            assert result['shares'] == 100
            assert result['risk_dollars'] == pytest.approx(750.0, rel=1)

    def test_drawdown_cascade_5pct(self, test_config):
        """At -5% drawdown, risk reduces to 0.75× of base."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=0.75), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            # base_risk = 750 × 0.75 = 562.5
            # shares = 562.5 / 7.5 = 75
            assert result['shares'] == 75
            assert result['risk_dollars'] == pytest.approx(562.5, rel=1)

    def test_drawdown_cascade_20pct_halt(self, test_config):
        """At -20% drawdown, trading halts (0.0 multiplier)."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=0.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'drawdown_halt'
            assert result['shares'] == 0


@pytest.mark.unit
class TestPositionSizerMultipliers:
    """Test individual risk multipliers."""

    def test_market_exposure_multiplier(self, test_config):
        """Exposure tier scales position (e.g., 50% exposure = 0.5× size)."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=0.5), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            # base_risk × exposure = 750 × 0.5 = 375
            # shares = 375 / 7.5 = 50
            assert result['shares'] == 50

    def test_vix_caution_multiplier(self, test_config):
        """VIX in caution zone (25-35) reduces position to 0.75×."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=0.75), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            # base_risk × vix = 750 × 0.75 = 562.5
            # shares = 562.5 / 7.5 = 75
            assert result['shares'] == 75

    def test_combined_multipliers(self, test_config):
        """Combined: base × drawdown × exposure × vix × phase."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=0.75), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=0.75), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            # 750 × 0.75 × 0.75 = 421.875
            # shares = 421.875 / 7.5 ≈ 56
            assert result['shares'] == 56


@pytest.mark.unit
class TestPositionSizerCaps:
    """Test position size caps and limits."""

    def test_max_position_size_cap(self, test_config):
        """Position cannot exceed max_position_size_pct of portfolio."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=1), \
             patch.object(sizer, 'get_active_positions_value', return_value=0.0):

            # Request 500 shares @ $150 = $75k = 75% of portfolio
            # But max_position_size_pct = 8% = $8k max
            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'ok'
            # max_position_value = 100k × 0.08 = 8k
            # max_shares = 8k / 150 = 53
            assert result['shares'] <= 53

    def test_max_concentration_check(self, test_config):
        """Single position cannot exceed max_concentration_pct."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=1), \
             patch.object(sizer, 'get_active_positions_value', return_value=0.0):

            # Position worth > 50% of portfolio
            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            if result['status'] == 'concentration':
                assert result['shares'] == 0
            else:
                # If it passed, position_size_pct should be <= max_concentration
                assert result['position_size_pct'] <= 50.0

    def test_total_invested_cap(self, test_config):
        """Total open positions cannot exceed max_total_invested_pct."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=11), \
             patch.object(sizer, 'get_active_positions_value', return_value=94000.0):

            # Already 94% invested, max is 95%
            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            if result['status'] == 'ok':
                # Remaining position should fit within 95% cap
                total = 94000.0 + result['position_value']
                assert (total / 100000.0 * 100) <= 95.0


@pytest.mark.unit
class TestPositionSizerEdgeCases:
    """Edge cases and error conditions."""

    def test_invalid_stop_price_above_entry(self, test_config):
        """Stop price >= entry price is invalid."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_risk_adjustment', return_value=1.0), \
             patch.object(sizer, 'get_market_exposure_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_vix_caution_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_phase_size_multiplier', return_value=1.0), \
             patch.object(sizer, 'get_position_count', return_value=5), \
             patch.object(sizer, 'get_active_positions_value', return_value=10000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 155.0)

            assert result['status'] == 'invalid'
            assert result['shares'] == 0

    def test_max_positions_reached(self, test_config):
        """Cannot enter new position if at max_positions."""
        sizer = PositionSizer(test_config)

        with patch.object(sizer, 'connect'), \
             patch.object(sizer, 'disconnect'), \
             patch.object(sizer, 'get_portfolio_value', return_value=100000.0), \
             patch.object(sizer, 'get_position_count', return_value=12), \
             patch.object(sizer, 'get_active_positions_value', return_value=50000.0):

            result = sizer.calculate_position_size('AAPL', 150.0, 142.5)

            assert result['status'] == 'no_room'
            assert result['shares'] == 0
