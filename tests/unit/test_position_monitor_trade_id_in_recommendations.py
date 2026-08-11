#!/usr/bin/env python3
"""Regression test: PositionMonitor's recommendation dicts must include 'trade_id'.

Found live 2026-08-03 via an end-to-end synthetic verification test (0 real open
positions existed in this dev environment all session, so this path was never
exercised): _persist_review() requires rec["trade_id"], but neither of
_evaluate_position()'s two return paths ever supplied that key - the early stop-hit
return used a bogus getattr(self, 'trade_ids', None) (self.trade_ids is never set,
always None), and the normal return path had no trade_id/trade_ids key at all. So
review_positions() raised KeyError('trade_id') for EVERY real position review,
unconditionally, regardless of exit trigger type.

FOLLOW-UP FIX (same day): the first fix selected `p.trade_ids` (a varchar column),
but that column is dead - never written by any code path. algo_positions' real,
actively-populated trade-reference column is `trade_ids_arr` (a Postgres array; see
executor_entry_handler.py's INSERT and every other consumer: Phase 6/8/9,
circuit_breaker.py, exposure_policy.py, executor_exit_handler.py, exit_engine.py,
position_sizer.py). Selecting `trade_ids` didn't crash but silently produced
trade_id=None for every real position - confirmed live against 3 real paper positions
opened 2026-08-03 (TGS/VIST/LPG all had trade_ids=NULL, trade_ids_arr=['TRD-...']).
Fixed to select/index trade_ids_arr instead; rows below now use a list, not a
comma-joined string.
"""

from datetime import date
from unittest.mock import patch

from algo.monitoring.position_monitor import PositionMonitor


class TestEvaluatePositionIncludesTradeId:
    def _make_monitor(self):
        return PositionMonitor(config={"max_hold_days": 90, "move_be_at_r": 1.5})

    def _row(self, trade_ids_arr):
        # Row shape matches the SELECT in review_positions()/_review_with_cursor():
        # (position_id, symbol, entry_price, stop_loss_price, t1, t2, t3, entry_date,
        #  created_at, quantity, target_levels_hit, trade_ids_arr, current_stop, current_price)
        return (
            1,
            "AAPL",
            320.0,
            315.0,
            None,
            None,
            None,
            date(2026, 7, 27),
            date(2026, 7, 27),
            1,
            0,
            trade_ids_arr,
            315.0,
            308.91,
        )

    def test_stop_loss_hit_path_includes_trade_id(self):
        monitor = self._make_monitor()
        # current_price ($308.91) <= active_stop ($315.0) triggers the stop-loss-hit fast
        # path, which returns before any further DB lookups (RS/sector/earnings checks).
        with patch.object(monitor, "_fetch_current_market", return_value=(308.91, 5.0, 300.0, 300.0)):
            rec = monitor._evaluate_position(self._row(["TRD-ABC123"]), date(2026, 8, 3))
        assert rec["action"] == "EARLY_EXIT"
        assert "STOP_LOSS_HIT" in rec["flags"]
        assert rec["trade_id"] == "TRD-ABC123"

    def test_trade_ids_with_multiple_values_uses_first(self):
        monitor = self._make_monitor()
        with patch.object(monitor, "_fetch_current_market", return_value=(308.91, 5.0, 300.0, 300.0)):
            rec = monitor._evaluate_position(self._row(["TRD-ABC123", "TRD-DEF456"]), date(2026, 8, 3))
        assert rec["trade_id"] == "TRD-ABC123"

    def test_null_trade_ids_returns_none_not_error(self):
        monitor = self._make_monitor()
        with patch.object(monitor, "_fetch_current_market", return_value=(308.91, 5.0, 300.0, 300.0)):
            rec = monitor._evaluate_position(self._row(None), date(2026, 8, 3))
        assert rec["trade_id"] is None
