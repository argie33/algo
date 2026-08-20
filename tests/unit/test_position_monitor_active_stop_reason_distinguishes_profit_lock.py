#!/usr/bin/env python3
"""Regression test (2026-08-20, live-reproduced on MRK/CP): algo/monitoring/position_monitor.py's
_evaluate_position hard-stop branch always worded its action_reason as "STOP LOSS HIT"
regardless of whether active_stop was above or below entry_price.

active_stop is a trailing stop that only ever ratchets UP (see _compute_trailing_stop), so
once a position has run enough to hit target levels it can sit ABOVE entry_price - triggering
this same unconditional code path on a pullback that still locks in a real profit, not a loss.
Live cases: MRK (entry $135.97, exit $143.42, +5.48%) and CP (entry $93.92, exit $98.40,
+4.77%) both closed with action_reason "STOP LOSS HIT: price $X <= stop $Y" despite being
winning trades - misleading anyone reading algo_trades.exit_reason directly (dashboard, trade
history, notifications).

Same bug class already fixed in exit_engine.py's active_stop branch on 2026-08-18 (see
test_exit_engine_active_stop_reason_distinguishes_profit_lock.py, live-reproduced on PDEX
there) but never applied to this separate, parallel "hard stop" implementation in
position_monitor.py. This fix mirrors that wording split exactly.
"""

from datetime import date
from unittest.mock import patch

from algo.monitoring.position_monitor import PositionMonitor


def _row(entry_price, init_stop, current_stop_price):
    # Matches the SELECT shape in review_positions()/_review_with_cursor().
    return (
        1,
        "MRK",
        entry_price,
        init_stop,
        None,
        None,
        None,
        date(2026, 8, 18),
        date(2026, 8, 18),
        25,
        3,
        ["TRD-1"],
        current_stop_price,
        None,
    )


class TestActiveStopReasonDistinguishesProfitLock:
    def _make_monitor(self):
        return PositionMonitor(
            config={
                "max_hold_days": 90,
                "move_be_at_r": 1.5,
                "max_distribution_days": 5,
                "position_halt_flag_count": 3,
            }
        )

    def test_active_stop_raised_above_entry_is_worded_as_locked_in_gain(self):
        """MRK's real numbers: active_stop ($140.00) raised above entry ($135.97) by
        target-hit raises - the exit is a win, not a loss, and must be worded that way."""
        monitor = self._make_monitor()
        row = _row(entry_price=135.97, init_stop=120.00, current_stop_price=140.00)
        with patch.object(monitor, "_fetch_current_market", return_value=(139.00, 5.0, 130.0, 130.0)):
            rec = monitor._evaluate_position(row, date(2026, 8, 19))

        assert rec["action"] == "EARLY_EXIT"
        assert "STOP_LOSS_HIT" in rec["flags"]
        assert "trailing stop" in rec["action_reason"].lower()
        assert "locked-in gain" in rec["action_reason"].lower()
        assert "stop loss hit" not in rec["action_reason"].lower()

    def test_active_stop_below_entry_still_worded_as_stop_loss_hit(self):
        """Sanity check: a genuine loss-cutting stop (active_stop below entry_price) must
        keep the original, accurate "STOP LOSS HIT" wording - this fix only changes wording
        for the profit-lock case, not real stop-losses."""
        monitor = self._make_monitor()
        row = _row(entry_price=120.0, init_stop=110.405, current_stop_price=110.405)
        with patch.object(monitor, "_fetch_current_market", return_value=(108.53, 5.0, 112.0, 112.0)):
            rec = monitor._evaluate_position(row, date(2026, 8, 8))

        assert rec["action"] == "EARLY_EXIT"
        assert "STOP_LOSS_HIT" in rec["flags"]
        assert "stop loss hit" in rec["action_reason"].lower()
        assert "locked-in gain" not in rec["action_reason"].lower()
