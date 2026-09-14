#!/usr/bin/env python3
"""Regression test for a real-money-readiness fix in
algo/orchestration/position_sync.py::sync_positions_from_trades().

BUG FOUND: the existing-position UPDATE branch resolves TWO position ids independently -
`trade_position_id` from a symbol-only lookup on algo_trades (most recent non-fully-exited
trade), and `existing_id` from a separate symbol-only lookup on algo_positions (preferring
'open', else most-recently-updated). Nothing verified these two agreed before this fix: the
branch used `trade_position_id` to pull trade_ids_arr/stop_loss_price/targets and wrote them
onto `existing_id`'s row via `UPDATE ... WHERE position_id = existing_id`. If a symbol ever
has algo_trades rows spanning two different position_id values that both look "currently
open" by each query's own criteria - the exact corruption class already seen once in
production (GEN/TRD-D9501EE6A4, referenced in executor_exit_handler.py's
_fetch_and_lock_trade_data) - this would splice one position's trades/stop-loss/targets onto
a DIFFERENT position's row: the actual corruption mechanism, not just a downstream symptom
of it.

Fixed by refusing to merge (logging CRITICAL and skipping the symbol as an error) whenever
trade_position_id and existing_id disagree, rather than silently writing cross-contaminated
data.
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.position_sync import sync_positions_from_trades


def _queue_side_effect(values, default):
    values = list(values)

    def _side_effect(*_args, **_kwargs):
        return values.pop(0) if values else default

    return _side_effect


class TestPositionSyncPositionIdMismatchGuard:
    def test_mismatched_position_ids_are_refused_not_merged(self):
        """trade_position_id ('pos-STALE') disagrees with existing_id ('pos-REAL') - must
        not run the UPDATE at all, and must record an error rather than silently proceeding."""
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchall.side_effect = _queue_side_effect([[("TEST", 10)]], [])

        trade_row = (100.0, "pos-STALE", 95.0, None, None, None, None, None, None)
        existing_row = ("pos-REAL", "open")

        cur.fetchone.side_effect = _queue_side_effect([trade_row, existing_row], None)

        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.orchestration.position_sync.DatabaseContext", return_value=mock_db_context):
            inserted, updated, errors, error_details = sync_positions_from_trades()

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions SET quantity" in c.args[0]]
        assert not update_calls, "must not run the merge UPDATE when position ids disagree"
        assert inserted == 0
        assert updated == 0
        assert errors == 1
        assert len(error_details) == 1
        assert error_details[0]["symbol"] == "TEST"
        assert "position_id mismatch" in error_details[0]["reason"]

    def test_matching_position_ids_still_update_normally(self):
        """Sanity check: the overwhelmingly common case (trade_position_id == existing_id)
        must be entirely unaffected by the new guard."""
        cur = MagicMock()
        cur.rowcount = 1
        cur.fetchall.side_effect = _queue_side_effect([[("TEST", 10)]], [])

        trade_row = (100.0, "pos-1", 95.0, None, None, None, None, None, None)
        existing_row = ("pos-1", "open")
        array_agg_result = (["trade-1"],)

        cur.fetchone.side_effect = _queue_side_effect([trade_row, existing_row, array_agg_result], None)

        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.orchestration.position_sync.DatabaseContext", return_value=mock_db_context):
            inserted, updated, errors, error_details = sync_positions_from_trades()

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions SET quantity" in c.args[0]]
        assert update_calls, "matching position ids must still run the normal UPDATE"
        assert updated == 1
        assert errors == 0
