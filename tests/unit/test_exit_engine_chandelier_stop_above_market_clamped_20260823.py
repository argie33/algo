"""Regression test for a 2026-08-23 fix in algo/trading/exit_engine.py::
PositionContext.check_chandelier_trail(): the chandelier/21-EMA trailing stop
(_chandelier_or_ema_stop) derives its value from lagging EOD reference data
(price_daily/technical_data_daily's highest-high/ATR, or the 21-EMA of daily closes) -
neither is bounded by the live current price, which can already have gapped down well
below what that stale reference data implies.

check_chandelier_trail only checked `chand_stop > self.active_stop` (does it tighten the
existing stop?) with no comparison against `self.cur_price` at all. Unlike
position_monitor.py's parallel "hard stop" implementation (which clamps right after its
equivalent trailing-stop calculation), NOTHING downstream of this function - execute_exit,
executor_exit_handler.py's _raise_stop_only - ever compares the new stop against current
price either; _raise_stop_only only checks it's higher than the EXISTING stop. An
above-market stop written to algo_positions.current_stop_price would make the very next
evaluation's `cur_price <= active_stop` check fire immediately, force-exiting the position
without any further adverse price movement.

Fixed by clamping chand_stop to just under self.cur_price before returning it, at the same
point position_monitor.py's equivalent check lives.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.exit_engine import PositionContext

CONFIG = {
    "exit_on_rs_line_break_50dma": False,
    "max_hold_days": 60,
    "eight_week_rule_threshold_pct": 5.0,
    "eight_week_rule_window_days": 56,
    "use_chandelier_trail": True,
}


def _make_context(**overrides) -> PositionContext:
    kwargs = {
        "symbol": "TESTX",
        "current_date": date(2026, 8, 23),
        "cur_price": Decimal("150.00"),
        "prev_close": Decimal("148.00"),
        "entry_price": Decimal("100.00"),
        "active_stop": Decimal("95.00"),
        "init_stop": Decimal("90.00"),
        "t1_price": Decimal("115.00"),
        "t2_price": Decimal("130.00"),
        "t3_price": Decimal("140.00"),
        "target_hits": 2,
        "days_held": 20,
        "dist_days_today": 0,
        "config": dict(CONFIG),
    }
    kwargs.update(overrides)
    return PositionContext(**kwargs)


class TestChandelierStopClampedToMarket:
    def test_stale_reference_stop_above_current_price_is_clamped(self):
        """Chandelier/EMA calc (from lagging EOD data) returns 160.00 - above the live
        current price of 150.00 (a gap-down scenario). Must be clamped to just under
        cur_price, not written above market."""
        ctx = _make_context(cur_price=Decimal("150.00"), active_stop=Decimal("95.00"))
        engine = MagicMock()
        engine._chandelier_or_ema_stop.return_value = 160.00

        triggered, signal = ctx.check_chandelier_trail(engine)

        assert triggered is True
        assert signal is not None
        assert signal["new_stop"] < 150.00, f"new_stop {signal['new_stop']} must be strictly below cur_price 150.00"
        assert signal["new_stop"] == 149.99

    def test_normal_stop_below_market_unaffected(self):
        """Sanity check: a chandelier stop that's already below current price (the normal
        case) must pass through unchanged."""
        ctx = _make_context(cur_price=Decimal("150.00"), active_stop=Decimal("95.00"))
        engine = MagicMock()
        engine._chandelier_or_ema_stop.return_value = 140.00

        triggered, signal = ctx.check_chandelier_trail(engine)

        assert triggered is True
        assert signal["new_stop"] == 140.00

    def test_no_trail_when_stop_not_tighter_than_existing(self):
        """Sanity check: if the computed stop isn't above the existing active_stop, no
        trail-up action is proposed at all (unrelated to the clamp fix)."""
        ctx = _make_context(cur_price=Decimal("150.00"), active_stop=Decimal("145.00"))
        engine = MagicMock()
        engine._chandelier_or_ema_stop.return_value = 140.00  # below active_stop

        triggered, signal = ctx.check_chandelier_trail(engine)

        assert triggered is False
        assert signal is None
