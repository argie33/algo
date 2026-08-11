#!/usr/bin/env python3
"""Regression test for a 2026-08-10 fix in algo/orchestration/position_sync.py::
sync_positions_from_trades().

sync_positions_from_trades() runs before Phase 1 on EVERY orchestrator invocation (see
orchestrator.py's _executor_phase_1: "Ensures algo_positions table stays in sync with actual
trades throughout the day"). Its existing-position UPDATE branch previously set
`current_stop_price = stop_loss_price` (the trade's ORIGINAL entry-time stop) unconditionally -
including for positions that are ALREADY OPEN, not just ones being genuinely reopened from
'closed'. That silently wiped out every legitimate stop-raise (from exposure_policy's
tighten_stop, position_monitor's RAISE_STOP, or ExitEngine's breakeven/chandelier trail) back
to the original stop at the start of the very next orchestrator run.

Live-confirmed via real data: every open position in the DB showed current_stop_price exactly
equal to stop_loss_price, which looked like "stops haven't been raised yet" but is exactly the
signature of every raise being reset before it could ever persist across a run boundary.

Fixed: only reset current_stop_price to stop_loss_price when reopening a previously-CLOSED
position (a genuine fresh start) - preserve it via a SQL CASE referencing the pre-update
`status` column for an already-open position.
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.position_sync import sync_positions_from_trades


def _queue_side_effect(values, default):
    values = list(values)

    def _side_effect(*_args, **_kwargs):
        return values.pop(0) if values else default

    return _side_effect


def _run_sync_for_existing_position(existing_status):
    cur = MagicMock()
    cur.rowcount = 1
    cur.fetchall.side_effect = _queue_side_effect([[("TEST", 10)]], [])

    trade_row = (100.0, "pos-1", 95.0, None, None, None, None, None, None)
    existing_row = ("pos-1", existing_status)
    array_agg_result = (["trade-1"],)

    cur.fetchone.side_effect = _queue_side_effect(
        [trade_row, existing_row, array_agg_result],
        None,
    )

    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)

    with patch("algo.orchestration.position_sync.DatabaseContext", return_value=mock_db_context):
        sync_positions_from_trades()

    update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions SET quantity" in c.args[0]]
    assert update_calls, "expected the existing-position UPDATE to run"
    return update_calls[0]


class TestPositionSyncPreservesRaisedStop:
    def test_update_sql_uses_case_guard_not_unconditional_overwrite(self):
        """The core fix: current_stop_price must never be a bare `= %s` in this UPDATE -
        it must be gated by a CASE on the pre-update status."""
        call = _run_sync_for_existing_position("open")
        sql = call.args[0]
        assert "current_stop_price = CASE WHEN status = %s THEN %s ELSE current_stop_price END" in sql, (
            f"expected a CASE-guarded current_stop_price assignment, got SQL: {sql}"
        )

    def test_reopen_case_still_resets_stop_to_original(self):
        """Sanity check: reopening a previously-closed position must still reset
        current_stop_price to stop_loss_price (a genuine fresh start) - the CASE condition
        compares against 'closed'."""
        call = _run_sync_for_existing_position("closed")
        sql, params = call.args[0], call.args[1]
        assert "CASE WHEN status = %s THEN %s ELSE current_stop_price END" in sql
        # params: (total_qty, 'open', stop_loss_price, 'closed', stop_loss_price, trade_ids_text, trade_ids_arr, existing_id)
        assert params[3] == "closed"
        assert params[4] == 95.0  # the trade's stop_loss_price, used as the reset target

    def test_no_bare_unconditional_current_stop_price_overwrite_remains(self):
        """Source-level guard against reintroducing the bug: this file must not contain a
        bare `current_stop_price = %s` assignment anywhere."""
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "algo" / "orchestration" / "position_sync.py").read_text(
            encoding="utf-8"
        )
        assert "current_stop_price = %s" not in source, (
            "found a bare `current_stop_price = %s` assignment - it must be CASE-guarded so "
            "an already-open position's stop-raise history is never reset by a routine sync"
        )
