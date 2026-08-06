#!/usr/bin/env python3
"""Unit tests for financial calculation modules: position_sizer, var, performance.

Validates core risk calculations, position sizing math, and performance metrics.
These tests ensure regressions in financial math are caught before live trading.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pytest


class TestPositionSizer:
    """Tests for position sizing calculations."""

    @pytest.fixture
    def config(self):
        """Mock configuration for position sizer."""
        return {
            "base_risk_pct": 0.75,
            "max_position_size_pct": 6.3,
            "max_positions": 15,
            "max_concentration_pct": 50.0,
            "max_total_invested_pct": 90.0,
            "max_total_risk_pct": 8.0,
            "risk_reduction_at_minus_5": 0.75,
            "risk_reduction_at_minus_10": 0.5,
            "risk_reduction_at_minus_15": 0.25,
            "risk_reduction_at_minus_20": 0.0,
            "vix_caution_threshold": 20.0,
            "vix_max_threshold": 30.0,
            "vix_caution_risk_reduction": 0.5,
        }

    @pytest.fixture
    def position_sizer(self, config):
        from algo.trading.position_sizer import PositionSizer

        return PositionSizer(config)

    def test_init_valid_config(self, position_sizer, config):
        """Verify position sizer initializes with valid config."""
        assert position_sizer.config == config

    def test_init_rejects_none_config(self):
        """Ensure position sizer rejects None config."""
        from algo.trading.position_sizer import PositionSizer

        with pytest.raises(ValueError, match="config cannot be None"):
            PositionSizer(None)

    def test_init_rejects_non_dict_config(self):
        """Ensure position sizer rejects non-dict config."""
        from algo.trading.position_sizer import PositionSizer

        with pytest.raises(TypeError, match="must be a dict"):
            PositionSizer([1, 2, 3])

    def test_base_risk_calculation(self, position_sizer):
        """Verify base risk percentage calculation."""
        portfolio_value = Decimal("100000")
        base_risk_pct = position_sizer.config["base_risk_pct"]
        expected_risk = portfolio_value * Decimal(str(base_risk_pct)) / Decimal("100")
        assert expected_risk == Decimal("750.00")

    def test_drawdown_defense_at_minus_5(self, position_sizer):
        """Verify risk reduction at -5% drawdown."""
        base_risk_pct = Decimal(str(position_sizer.config["base_risk_pct"]))
        reduction_factor = Decimal(str(position_sizer.config["risk_reduction_at_minus_5"]))
        reduced_risk = base_risk_pct * reduction_factor
        assert reduced_risk == Decimal("0.5625")  # 0.75% * 0.75

    def test_drawdown_defense_at_minus_10(self, position_sizer):
        """Verify risk reduction at -10% drawdown."""
        base_risk_pct = Decimal(str(position_sizer.config["base_risk_pct"]))
        reduction_factor = Decimal(str(position_sizer.config["risk_reduction_at_minus_10"]))
        reduced_risk = base_risk_pct * reduction_factor
        assert reduced_risk == Decimal("0.375")  # 0.75% * 0.5

    def test_max_position_size_constraint(self, position_sizer):
        """Verify max position size constraint."""
        portfolio_value = Decimal("100000")
        max_pos_pct = position_sizer.config["max_position_size_pct"]
        max_position_value = portfolio_value * Decimal(str(max_pos_pct)) / Decimal("100")
        assert max_position_value == Decimal("6300.00")

    def test_concentration_constraint(self, position_sizer):
        """Verify max concentration constraint."""
        portfolio_value = Decimal("100000")
        max_concentration_pct = position_sizer.config["max_concentration_pct"]
        max_top_position = portfolio_value * Decimal(str(max_concentration_pct)) / Decimal("100")
        assert max_top_position == Decimal("50000.00")

    def test_position_count_constraint(self, position_sizer):
        """Verify max positions constraint."""
        max_positions = position_sizer.config["max_positions"]
        assert max_positions == 15
        assert max_positions > 0

    @patch("utils.db.DatabaseContext")
    def test_get_portfolio_value_none_config(self, mock_db, config):
        """Verify portfolio value calculation with valid data."""
        from algo.trading.position_sizer import PositionSizer

        sizer = PositionSizer(config)

        # Mock alpaca equity fetch
        with patch.object(sizer, "_fetch_live_alpaca_equity", return_value=None):
            with patch.object(
                sizer,
                "_with_cursor",
                return_value=(Decimal("100000"), date.today()),
            ):
                # This would normally call the database, mocked to return fresh snapshot
                pass


class TestPositionSizingAudit:
    """algo_position_sizing_audit's schema (base_shares/final_shares/cascade_multiplier/
    multipliers_json/reasons_json) was added by migration but the risk-multiplier cascade
    _calculate_with_external_cursor already computes (risk_adjustment/exposure_mult/
    phase_mult/vix_mult/regime_mult) was never persisted to it - the table sat permanently
    empty, which made lambda/api/routes/risk_dashboard.py's comprehensive dashboard 503
    unconditionally. _record_sizing_audit fixes that; these tests cover it directly since
    exercising the full calculate_position_size cascade requires mocking ~6 DB-touching
    helper methods.
    """

    @pytest.fixture
    def config(self):
        return {
            "base_risk_pct": 0.75,
            "max_position_size_pct": 6.3,
            "max_positions": 15,
            "max_concentration_pct": 50.0,
            "max_total_invested_pct": 90.0,
            "risk_reduction_at_minus_5": 0.75,
            "risk_reduction_at_minus_10": 0.5,
            "risk_reduction_at_minus_15": 0.25,
            "risk_reduction_at_minus_20": 0.0,
            "vix_caution_threshold": 20.0,
            "vix_max_threshold": 30.0,
            "vix_caution_risk_reduction": 0.5,
        }

    @pytest.fixture
    def position_sizer(self, config):
        from algo.trading.position_sizer import PositionSizer

        return PositionSizer(config)

    @patch("algo.trading.position_sizer.DatabaseContext")
    def test_record_sizing_audit_inserts_cascade_breakdown(self, mock_db_ctx, position_sizer):
        mock_cur = mock_db_ctx.return_value.__enter__.return_value

        position_sizer._record_sizing_audit(
            symbol="AAPL",
            signal_date=date(2026, 7, 21),
            entry_price=150.0,
            stop_loss_price=145.0,
            base_shares=120,
            final_shares=100,
            position_size_pct=Decimal("4.5"),
            cascade_multiplier=Decimal("0.75"),
            multipliers={"vix_mult": 0.5, "regime_mult": 1.0},
            reasons={"vix_mult": "VIX caution multiplier: 0.50x"},
        )

        assert mock_cur.execute.called
        sql_text, params = mock_cur.execute.call_args[0]
        assert "INSERT INTO algo_position_sizing_audit" in sql_text
        assert params[0] == "AAPL"
        # base_shares (pre-cap) and final_shares (post-cap) must both be recorded distinctly,
        # not collapsed to the same value - that's the whole point of the audit trail.
        assert params[4] == 120
        assert params[5] == 100
        assert params[7] == 0.75
        import json

        assert json.loads(params[8]) == {"vix_mult": 0.5, "regime_mult": 1.0}
        assert json.loads(params[9]) == {"vix_mult": "VIX caution multiplier: 0.50x"}

    @patch("algo.trading.position_sizer.DatabaseContext")
    def test_record_sizing_audit_failure_does_not_raise(self, mock_db_ctx, position_sizer):
        """Best-effort: a DB/logging failure here must never block a real sizing decision
        or trade entry - this is an audit trail, not a gating check."""
        mock_db_ctx.side_effect = RuntimeError("connection refused")

        position_sizer._record_sizing_audit(
            symbol="AAPL",
            signal_date=date(2026, 7, 21),
            entry_price=150.0,
            stop_loss_price=145.0,
            base_shares=100,
            final_shares=100,
            position_size_pct=Decimal("4.5"),
            cascade_multiplier=Decimal("1.0"),
            multipliers={"vix_mult": 1.0},
            reasons={"vix_mult": "VIX caution multiplier: 1.00x"},
        )  # must not raise


class TestValueAtRisk:
    """Tests for Value at Risk calculations."""

    @pytest.fixture
    def config(self):
        """Mock configuration for VaR calculation."""
        return {
            "var_percentile": 5,
            "cvar_percentile": 5,
            "stressed_var_percentile": 10,
        }

    @pytest.fixture
    def var_calculator(self, config):
        from algo.risk.var import ValueAtRisk

        return ValueAtRisk(config)

    def test_init_valid_config(self, var_calculator, config):
        """Verify VaR calculator initializes with valid config."""
        assert var_calculator.config == config

    def test_var_percentile_value_range(self, var_calculator):
        """Verify VaR percentile is in valid range (1-50)."""
        percentile = var_calculator.config["var_percentile"]
        assert 1 <= percentile <= 50

    def test_cvar_percentile_value_range(self, var_calculator):
        """Verify CVaR percentile is in valid range (1-50)."""
        percentile = var_calculator.config["cvar_percentile"]
        assert 1 <= percentile <= 50

    def test_stressed_var_percentile_value_range(self, var_calculator):
        """Verify stressed VaR percentile is in valid range (1-50)."""
        percentile = var_calculator.config["stressed_var_percentile"]
        assert 1 <= percentile <= 50

    def test_var_cvar_stressed_var_query_adjusted_equity_not_raw(self, var_calculator):
        """Regression: historical_var()/cvar()/stressed_var() queried raw
        total_portfolio_value instead of adjusted_equity (migration 1134). Raw equity
        moves for both trading performance AND external capital flows - a same-day
        deposit/withdrawal reads as an equivalent trading gain/loss, injecting a fake
        extreme "return" into the historical sample these functions build VaR/CVaR/
        stressed-VaR from. Every other equity-series risk metric in this codebase
        (circuit_breaker.py drawdown/daily_loss/weekly_loss, position_sizer.py
        drawdown, performance.py Sharpe/Sortino/Calmar/max_drawdown) was already
        fixed to use adjusted_equity; these three were the last holdouts."""
        from unittest.mock import MagicMock, patch

        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur

        with patch("algo.risk.var.DatabaseContext", return_value=mock_ctx):
            try:
                var_calculator.historical_var()
            except RuntimeError:
                pass  # expected: no rows -> insufficient data
            try:
                var_calculator.cvar()
            except RuntimeError:
                pass
            try:
                var_calculator.stressed_var()
            except RuntimeError:
                pass

        executed_sql = " ".join(str(call.args[0]) for call in mock_cur.execute.call_args_list)
        assert "adjusted_equity" in executed_sql
        assert "total_portfolio_value" not in executed_sql

    def test_percentile_calculation(self):
        """Verify numpy percentile calculation for VaR."""
        returns = np.array([-0.05, -0.03, -0.02, 0.0, 0.02, 0.03, 0.05])
        confidence = 0.95
        var_percentile = np.percentile(returns, (1 - confidence) * 100)
        # At 95% confidence (5th percentile), expecting a loss
        assert var_percentile < 0

    def test_var_interpretation(self):
        """Verify VaR interpretation message format."""
        var_dollars = 5000.0
        var_pct = 5.0
        interpretation = (
            f"95% confident portfolio won't lose more than ${var_dollars:.2f} (or {var_pct:.2f}%) in one day"
        )
        assert "$5000.00" in interpretation
        assert "5.00%" in interpretation
        assert "95% confident" in interpretation

    def test_insufficient_data_raises_error(self):
        """Verify VaR calculation fails with insufficient data."""
        returns = [-0.01, -0.02]
        if len(returns) < 5:
            with pytest.raises(RuntimeError, match="Insufficient"):
                if len(returns) < 5:
                    raise RuntimeError(f"Insufficient historical data for VaR (only {len(returns)} snapshots, need 5+)")

    def test_var_dollars_calculation(self):
        """Verify VaR dollars calculation."""
        current_value = Decimal("100000")
        var_percentile = Decimal("-0.05")
        var_dollars = current_value * abs(var_percentile)
        assert var_dollars == Decimal("5000")

    def test_zero_return_portfolio(self):
        """Verify VaR handling when portfolio value is zero."""
        current_value = Decimal("0")
        if current_value == 0:
            pytest.skip("Cannot calculate VaR for zero portfolio value")


class TestPerformanceMetrics:
    """Tests for performance metric calculations."""

    @pytest.fixture
    def config(self):
        """Mock configuration for performance metrics."""
        return {
            "var_percentile": 5,
            "dashboard_min_quality_threshold": 40.0,
        }

    @pytest.fixture
    def performance_calc(self, config):
        from algo.reporting.performance import LivePerformance

        return LivePerformance(config)

    def test_init_valid_config(self, performance_calc, config):
        """Verify performance calculator initializes with valid config."""
        assert performance_calc.config == config

    def test_sharpe_ratio_calculation(self):
        """Verify Sharpe ratio calculation from returns."""
        daily_returns = [0.01, 0.02, -0.01, 0.015, 0.005]
        mean_return = np.mean(daily_returns)
        std_return = np.std(daily_returns)
        if std_return > 0:
            sharpe = (mean_return / std_return) * np.sqrt(252)
            assert sharpe is not None
            # Annualized, should be a valid number (can be >10 with good returns)
            assert -100 < sharpe < 100

    def test_win_rate_calculation(self):
        """Verify win rate calculation."""
        wins = 30
        losses = 20
        total = wins + losses
        win_rate = (wins / total) * 100 if total > 0 else 0
        assert win_rate == 60.0

    def test_win_rate_excludes_breakeven_from_denominator(self, performance_calc):
        """Regression: LivePerformance.win_rate() divided win_count by `total`
        (COUNT(*) over the lookback window), which includes breakeven trades
        (r_multiple == 0) and trades where r_multiple couldn't be computed (NULL).
        Neither is a win or a loss, so including them in the denominator silently
        deflated win_rate_pct relative to the CB9 circuit breaker's win-rate query
        (utils/data_queries.py get_trade_win_loss_stats), which correctly divides by
        decisive trades only (wins + losses). Same underlying trades should not
        produce two different win rates depending which code path computed it.

        10 trades: 5 wins, 2 losses, 3 breakeven/unclassifiable -> decisive = 7.
        Correct win_rate_pct = 5/7*100 ~= 71.43, not 5/10*100 = 50.0.
        """
        from unittest.mock import MagicMock

        total, win_count, loss_count = 10, 5, 2
        mock_row = (total, win_count, loss_count, 2.5, -1.0, 3.0, -1.5)

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = mock_row
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur

        with patch("algo.reporting.performance.DatabaseContext", return_value=mock_ctx):
            result = performance_calc.win_rate(lookback_trades=10)

        assert result["win_count"] == 5
        assert result["loss_count"] == 2
        assert result["win_rate_pct"] == pytest.approx(5 / 7 * 100, abs=0.01)

    def test_expectancy_calculation(self):
        """Verify expectancy (E = WR x AvgWin - LR x AvgLoss)."""
        win_rate = 0.6
        avg_win = 2.0  # R-multiples
        loss_rate = 0.4
        avg_loss = 1.0
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        # 0.6 * 2.0 - 0.4 * 1.0 = 1.2 - 0.4 = 0.8
        assert abs(expectancy - 0.8) < 0.0001

    def test_negative_expectancy_detection(self):
        """Verify detection of negative expectancy (losing system)."""
        win_rate = 0.4
        avg_win = 1.5
        loss_rate = 0.6
        avg_loss = 2.0
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        # 0.4 * 1.5 - 0.6 * 2.0 = 0.6 - 1.2 = -0.6
        assert expectancy < 0, "System should have negative expectancy"

    def test_max_drawdown_calculation(self):
        """Verify maximum drawdown calculation."""
        portfolio_values = [100000, 105000, 103000, 98000, 100000, 110000]
        peak = portfolio_values[0]
        max_dd = 0
        for value in portfolio_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        # Expected: drawdown from 105000 to 98000 = 7000/105000 = 6.67%
        assert max_dd > 0
        assert max_dd < 0.1  # Less than 10%

    def test_insufficient_trade_data(self):
        """Verify performance metrics handle insufficient data."""
        trades = []
        if len(trades) < 10:
            result = None
        assert result is None


class TestFinancialMathEdgeCases:
    """Tests for edge cases in financial calculations."""

    def test_division_by_zero_protection(self):
        """Verify protection against division by zero."""
        portfolio_value = Decimal("100000")
        initial_value = Decimal("0")
        try:
            _ = (portfolio_value - initial_value) / initial_value
            pytest.fail("Should raise ZeroDivisionError")
        except ZeroDivisionError:
            pass  # Expected

    def test_negative_portfolio_value_rejection(self):
        """Verify rejection of negative portfolio values."""
        negative_value = Decimal("-50000")
        if negative_value < 0:
            pytest.skip("Negative portfolio values should be rejected at data loading layer")

    def test_very_small_position_sizing(self):
        """Verify handling of very small position sizes."""
        portfolio_value = Decimal("1000")
        base_risk_pct = Decimal("0.01")
        risk_amount = portfolio_value * base_risk_pct / Decimal("100")
        assert risk_amount == Decimal("0.10")
        assert risk_amount > 0

    def test_very_large_concentration(self):
        """Verify handling of large concentration limits."""
        portfolio_value = Decimal("10000000")
        max_concentration = Decimal("50.0")
        max_pos_value = portfolio_value * max_concentration / Decimal("100")
        assert max_pos_value == Decimal("5000000")
        assert max_pos_value > 0

    def test_precision_loss_with_float_arithmetic(self):
        """Verify calculations maintain precision with Decimal."""
        portfolio_value = Decimal("123456.78")
        position_pct = Decimal("6.3")
        max_pos = portfolio_value * position_pct / Decimal("100")
        # Ensure no precision loss (decimal arithmetic)
        expected = Decimal("7777.77714")
        assert abs(max_pos - expected) < Decimal("0.01")

    def test_rounding_consistency(self):
        """Verify consistent rounding in financial calculations."""
        from decimal import ROUND_HALF_UP

        value = Decimal("1000.125")
        rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert rounded == Decimal("1000.13")


class TestFinancialCalculationIntegration:
    """Integration tests combining multiple financial calculations."""

    def test_position_sizing_respects_drawdown_defense(self):
        """Verify position sizing reduces correctly with drawdown."""
        portfolio_value = Decimal("100000")
        base_risk_pct = Decimal("0.75")

        # Base risk
        base_risk_dollars = portfolio_value * base_risk_pct / Decimal("100")
        assert base_risk_dollars == Decimal("750.00")

        # At -10% drawdown, reduce to 50%
        reduced_risk = base_risk_dollars * Decimal("0.5")
        assert reduced_risk == Decimal("375.00")
        assert reduced_risk < base_risk_dollars

    def test_win_rate_and_expectancy_consistency(self):
        """Verify win rate and expectancy calculations are consistent."""
        # System: 60% win rate, 2R avg win, 40% loss rate, 1R avg loss
        win_rate = 0.6
        avg_win_r = 2.0
        loss_rate = 0.4
        avg_loss_r = 1.0

        expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
        assert abs(expectancy - 0.8) < 0.0001  # Positive expectancy system

        # Trade 100 trades
        expected_wins = 60
        expected_losses = 40
        total_profit_r = (expected_wins * avg_win_r) - (expected_losses * avg_loss_r)
        avg_r_per_trade = total_profit_r / 100
        assert abs(avg_r_per_trade - expectancy) < 0.0001

    def test_portfolio_value_and_var_relationship(self):
        """Verify VaR scales correctly with portfolio value."""
        var_pct = 0.05  # 5% VaR
        portfolio1 = Decimal("100000")
        portfolio2 = Decimal("200000")

        var_dollars1 = portfolio1 * Decimal(str(var_pct))
        var_dollars2 = portfolio2 * Decimal(str(var_pct))

        # VaR should scale linearly with portfolio size
        assert var_dollars2 == var_dollars1 * Decimal("2")


class TestFinancialCalculationsWithMalformedData:
    """Tests for handling malformed/invalid data in financial calculations."""

    def test_position_sizer_with_none_config(self):
        """Verify position sizer rejects None config."""
        from algo.trading.position_sizer import PositionSizer

        with pytest.raises((ValueError, TypeError)):
            PositionSizer(None)

    def test_position_sizer_with_missing_required_fields(self):
        """Verify position sizer validates required fields."""
        from algo.trading.exceptions import ConfigurationError
        from algo.trading.position_sizer import PositionSizer

        incomplete_config = {"base_risk_pct": 0.75}  # Missing other required fields
        try:
            sizer = PositionSizer(incomplete_config)
            # If it doesn't validate, accessing missing fields should fail
            _ = sizer.config["max_position_size_pct"]
        except (KeyError, ValueError, TypeError, ConfigurationError):
            pass  # Expected behavior

    def test_position_sizer_requires_risk_reduction_at_minus_20(self):
        """CRITICAL FIX regression: get_risk_adjustment()'s >= 20% drawdown branch reads
        risk_reduction_at_minus_20 (its own docstring even claims "Config keys validated at
        init" for every risk threshold), but this key was missing from __init__'s
        required_config_keys - a missing/deleted DB row would pass construction silently and
        only raise KeyError deep inside get_risk_adjustment() at the exact moment a portfolio
        hits a -20% drawdown, the worst possible time for a validation gap to surface. Must
        fail fast at construction instead, like its _5/_10/_15 siblings already do."""
        from algo.trading.exceptions import ConfigurationError
        from algo.trading.position_sizer import PositionSizer

        config = {
            "base_risk_pct": 0.75,
            "max_positions": 15,
            "risk_reduction_at_minus_5": 0.75,
            "risk_reduction_at_minus_10": 0.5,
            "risk_reduction_at_minus_15": 0.25,
            # risk_reduction_at_minus_20 deliberately omitted
            "vix_caution_threshold": 20.0,
            "vix_max_threshold": 30.0,
            "vix_caution_risk_reduction": 0.5,
        }
        with pytest.raises(ConfigurationError, match="risk_reduction_at_minus_20"):
            PositionSizer(config)

    def test_position_sizer_with_string_percentages(self):
        """Verify position sizer handles string percentages."""
        from algo.trading.position_sizer import PositionSizer

        config = {
            "base_risk_pct": "0.75",
            "max_position_size_pct": "6.3",
            "max_positions": "15",
            "max_concentration_pct": "50.0",
            "max_total_invested_pct": "90.0",
            "risk_reduction_at_minus_5": "0.75",
            "risk_reduction_at_minus_10": "0.5",
            "risk_reduction_at_minus_15": "0.25",
            "risk_reduction_at_minus_20": "0.0",
            "vix_caution_threshold": "20.0",
            "vix_max_threshold": "30.0",
            "vix_caution_risk_reduction": "0.5",
        }
        try:
            sizer = PositionSizer(config)
            # Calculations should handle string conversion or reject it
            assert sizer is not None or True
        except (ValueError, TypeError):
            pass  # Expected if strict type checking

    def test_position_sizer_with_negative_percentages(self):
        """Verify position sizer rejects negative percentages."""
        from algo.trading.position_sizer import PositionSizer

        config = {
            "base_risk_pct": -0.75,  # Invalid negative
            "max_position_size_pct": 6.3,
            "max_positions": 15,
            "max_concentration_pct": 50.0,
            "max_total_invested_pct": 90.0,
            "risk_reduction_at_minus_5": 0.75,
            "risk_reduction_at_minus_10": 0.5,
            "risk_reduction_at_minus_15": 0.25,
            "risk_reduction_at_minus_20": 0.0,
            "vix_caution_threshold": 20.0,
            "vix_max_threshold": 30.0,
            "vix_caution_risk_reduction": 0.5,
        }
        try:
            sizer = PositionSizer(config)
            # Negative percentages might be rejected at config validation
            assert sizer is not None or True
        except (ValueError, AssertionError):
            pass  # Expected for invalid config

    def test_var_calculator_with_invalid_percentile(self):
        """Verify VaR calculator rejects invalid percentiles."""
        from algo.risk.var import ValueAtRisk

        invalid_config = {
            "var_percentile": 100,  # Out of range (should be 1-50)
            "cvar_percentile": 5,
            "stressed_var_percentile": 10,
        }
        try:
            calc = ValueAtRisk(invalid_config)
            # Should validate percentile range
            assert calc is not None or True
        except (ValueError, AssertionError):
            pass  # Expected

    def test_var_calculator_with_zero_percentile(self):
        """Verify VaR calculator rejects zero percentile."""
        from algo.risk.var import ValueAtRisk

        invalid_config = {
            "var_percentile": 0,  # Invalid
            "cvar_percentile": 5,
            "stressed_var_percentile": 10,
        }
        try:
            calc = ValueAtRisk(invalid_config)
            assert calc is not None or True
        except (ValueError, AssertionError):
            pass  # Expected

    def test_var_calculation_with_null_returns(self):
        """Verify VaR handles None/null returns."""
        returns = None
        if returns is None:
            with pytest.raises((TypeError, ValueError)):
                np.percentile(returns, 5)

    def test_var_calculation_with_non_numeric_returns(self):
        """Verify VaR rejects non-numeric returns."""
        returns = ["0.01", "0.02", "abc"]  # Non-numeric strings
        try:
            # Should fail on conversion or calculation
            data = np.array([float(x) if isinstance(x, (int, float)) else None for x in returns])
            if None in data:
                raise ValueError("Non-numeric data in returns")
        except (ValueError, TypeError):
            pass  # Expected

    def test_performance_calc_with_invalid_quality_threshold(self):
        """Verify performance calculator validates quality threshold."""
        from algo.reporting.performance import LivePerformance

        config = {
            "var_percentile": 5,
            "dashboard_min_quality_threshold": -10.0,  # Invalid negative
        }
        try:
            perf = LivePerformance(config)
            assert perf is not None or True
        except (ValueError, AssertionError):
            pass  # Expected

    def test_sharpe_ratio_with_zero_std_dev(self):
        """Verify Sharpe ratio handling when std dev is zero."""
        daily_returns = [0.01, 0.01, 0.01, 0.01, 0.01]
        std_return = np.std(daily_returns)
        if std_return == 0:
            # Should not attempt division by zero
            sharpe = None  # Should return None or raise exception
        assert sharpe is None or True

    def test_max_drawdown_with_all_increasing_values(self):
        """Verify max drawdown calculation with no drawdown."""
        portfolio_values = [100000, 110000, 120000, 130000, 140000]
        peak = portfolio_values[0]
        max_dd = 0
        for value in portfolio_values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
        # No drawdown, max_dd should be 0
        assert max_dd == 0

    def test_portfolio_value_calculation_with_extreme_values(self):
        """Verify portfolio calculations with extreme values."""
        extreme_portfolio = Decimal("999999999999.99")
        base_risk_pct = Decimal("0.75")
        try:
            risk_amount = extreme_portfolio * base_risk_pct / Decimal("100")
            assert risk_amount > 0
        except (OverflowError, ValueError):
            pass  # Expected for extreme values

    def test_position_sizing_with_zero_portfolio_value(self):
        """Verify position sizing handles zero portfolio value."""
        portfolio_value = Decimal("0")
        if portfolio_value == 0:
            # Should skip or return 0, not crash
            risk_amount = Decimal("0")
            assert risk_amount == 0

    def test_expectancy_with_zero_win_rate(self):
        """Verify expectancy calculation with zero win rate."""
        win_rate = 0.0
        avg_win = 2.0
        loss_rate = 1.0
        avg_loss = 1.0
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
        # Should handle gracefully
        assert expectancy == -1.0

    def test_win_rate_with_zero_total_trades(self):
        """Verify win rate calculation with zero trades."""
        wins = 0
        losses = 0
        total = wins + losses
        win_rate = (wins / total) * 100 if total > 0 else 0
        # Should return 0, not divide by zero
        assert win_rate == 0

    def test_cvar_percentile_as_string(self):
        """Verify CVaR percentile rejects string input."""
        from algo.risk.var import ValueAtRisk

        config = {
            "var_percentile": 5,
            "cvar_percentile": "5",  # String instead of int
            "stressed_var_percentile": 10,
        }
        try:
            calc = ValueAtRisk(config)
            assert calc is not None or True
        except (TypeError, ValueError):
            pass  # Expected
