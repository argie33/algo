"""Regression tests for 4 NaN-comparison-guard gaps in algo/risk/circuit_breaker.py, found
2026-08-10 continuing the systematic sweep (`value <= 0` never catches NaN - NaN comparisons
are always False in Python; already fixed 15x elsewhere this session).

- _check_drawdown_re_engagement: bare float() on adjusted_equity, missing the file's own
  _float() NaN/Inf guard that the sibling _check_drawdown already uses on the same source.
- _check_weekly_loss: bare float() on cur_val/week_ago_val; the threshold a few lines below
  already had an explicit NaN check, but it was never applied to these two.
- _check_intraday_market_health: `prior <= 0` didn't catch NaN/Inf, and `latest` had no
  finiteness check at all, despite the function's own docstring promising a fail-closed halt
  on invalid SPY price data.
- _check_sector_drawdown: `cost_basis <= 0` didn't catch NaN/Inf, and unrealized_pnl had no
  finiteness check at all - either would silently corrupt a sector's summed P&L that feeds a
  real portfolio-wide halt decision.
- _check_daily_profit_cap: `prev_val <= 0` didn't catch NaN/Inf, and today_val had no
  finiteness check at all.
"""

from datetime import date
from unittest.mock import MagicMock

from algo.risk.circuit_breaker import CircuitBreaker


def _cb(**config):
    return CircuitBreaker(config=config)


class TestDrawdownReEngagementRejectsNaN:
    def test_nan_peak_treated_as_invalid_not_halted_false_positive(self):
        cur = MagicMock()
        cur.fetchone.return_value = (float("nan"), 100_000.0)
        cb = _cb()
        result = cb._check_drawdown_re_engagement(date(2026, 8, 10), cur)
        assert result["reason"] == "Invalid values"
        assert result["halted"] is False

    def test_zero_peak_still_treated_as_invalid(self):
        """Confirms the fix's _float(default=0.0) coercion didn't disturb the pre-existing
        `peak <= 0` invalid-value path for legitimately bad (non-NaN) data."""
        cur = MagicMock()
        cur.fetchone.return_value = (0.0, 90_000.0)
        cb = _cb()
        result = cb._check_drawdown_re_engagement(date(2026, 8, 10), cur)
        assert result["reason"] == "Invalid values"


class TestWeeklyLossRejectsNaN:
    def test_nan_current_value_fails_closed(self):
        cur = MagicMock()
        cur.fetchone.return_value = (float("nan"), 100_000.0)
        cb = _cb(max_weekly_loss_pct="10.0")
        result = cb._check_weekly_loss(date(2026, 8, 10), cur)
        assert result["halted"] is True
        assert "invalid" in result["reason"].lower()

    def test_nan_week_ago_value_fails_closed(self):
        cur = MagicMock()
        cur.fetchone.return_value = (100_000.0, float("nan"))
        cb = _cb(max_weekly_loss_pct="10.0")
        result = cb._check_weekly_loss(date(2026, 8, 10), cur)
        assert result["halted"] is True

    def test_normal_values_still_pass(self):
        cur = MagicMock()
        cur.fetchone.return_value = (105_000.0, 100_000.0)
        cb = _cb(max_weekly_loss_pct="10.0")
        result = cb._check_weekly_loss(date(2026, 8, 10), cur)
        assert result["halted"] is False


class TestIntradayMarketHealthRejectsNaN:
    def test_nan_latest_price_fails_closed(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (float("nan"), False, None),
            (450.0, False, None),
        ]
        cb = _cb()
        result = cb._check_intraday_market_health(date(2026, 8, 10), cur)
        assert result["halted"] is True
        assert "non-finite" in result["reason"].lower() or "invalid" in result["reason"].lower()

    def test_normal_prices_still_pass(self):
        cur = MagicMock()
        cur.fetchall.return_value = [
            (455.0, False, None),
            (450.0, False, None),
        ]
        cb = _cb()
        result = cb._check_intraday_market_health(date(2026, 8, 10), cur)
        assert result["halted"] is False


class TestSectorDrawdownRejectsNaN:
    def test_nan_unrealized_pnl_position_skipped_not_corrupted(self):
        rows = [
            ("Technology", float("nan"), 100.0, 100),
            ("Technology", -500.0, 100.0, 100),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cb = _cb(sector_drawdown_halt_pct="-12.0")
        result = cb._check_sector_drawdown(date(2026, 8, 10), cur)
        # Only the second (valid) position should count: -500/10000 = -5%, not NaN.
        assert result["value"] == -5.0

    def test_nan_entry_price_position_skipped(self):
        rows = [
            ("Technology", -500.0, float("nan"), 100),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cb = _cb(sector_drawdown_halt_pct="-12.0")
        result = cb._check_sector_drawdown(date(2026, 8, 10), cur)
        assert result["reason"] == "Insufficient data for sector drawdown check (positions missing P&L data)"


class TestDailyProfitCapRejectsNaN:
    def test_nan_prev_val_treated_as_insufficient_history(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [(100_000.0,), (float("nan"),)]
        cb = _cb(daily_profit_cap_pct="5.0")
        result = cb._check_daily_profit_cap(date(2026, 8, 10), cur)
        assert result["reason"] == "Insufficient history"

    def test_normal_values_still_compute(self):
        cur = MagicMock()
        cur.fetchone.side_effect = [(102_000.0,), (100_000.0,)]
        cb = _cb(daily_profit_cap_pct="5.0")
        result = cb._check_daily_profit_cap(date(2026, 8, 10), cur)
        assert result["value"] == 2.0
