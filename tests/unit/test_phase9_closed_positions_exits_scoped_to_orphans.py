#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: _record_closed_positions_exits' candidate SELECT
had no filter tying it to algo_trades - it picked up EVERY algo_positions row closed today,
including positions closed through the normal exit_engine.py -> executor_exit_handler.py
path, which already updates algo_trades (exit_date, exit_price, profit_loss_dollars,
status='closed') in the same transaction as the algo_positions close.

Every one of those already-recorded positions would then fail this function's own UPDATE
(`WHERE symbol = %s AND exit_date IS NULL`) with 0 rows affected, which is treated as a
hard data-integrity failure (see test_phase9_exit_recording_db_failure.py) - so this
function crashed Phase 9, and halted all trading, on ANY day with a normal, correctly
recorded exit. Live-reproduced 2026-07-27: 9 positions closed normally via exit_engine.py;
the first one processed (LPG) hit exactly this false failure.

The candidate SELECT must be scoped to positions whose algo_trades row is still open
(exit_date IS NULL) - i.e. genuinely orphaned closes (e.g. a broker-side close detected
only during reconciliation) - not ones the normal exit path already fully recorded.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def test_candidate_select_is_scoped_to_still_open_algo_trades():
    """The read-side SELECT must filter to positions whose algo_trades row still has
    exit_date IS NULL, so a normally-closed position (already fully recorded by
    exit_engine.py) is never picked up as a candidate in the first place."""
    read_cur = MagicMock()
    read_cur.fetchall.return_value = []  # no orphans - nothing further to assert on
    read_ctx = MagicMock()
    read_ctx.__enter__.return_value = read_cur
    read_ctx.__exit__.return_value = False

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=read_ctx):
        _record_closed_positions_exits(date(2026, 7, 27), MagicMock())

    select_sql = read_cur.execute.call_args[0][0]
    assert "algo_positions" in select_sql
    assert "algo_trades" in select_sql, (
        "the candidate SELECT must reference algo_trades to exclude positions the normal "
        "exit path already closed there - otherwise every ordinary exit crashes Phase 9"
    )
    assert "exit_date IS NULL" in select_sql


def test_normally_closed_position_is_not_processed():
    """End-to-end: a position whose algo_trades row is already closed (the normal case)
    must not reach the per-symbol UPDATE loop at all - simulated here by having the
    (real, unmocked-SQL-text) read cursor return zero rows, exactly what the fixed
    EXISTS filter produces for an all-already-closed batch."""
    read_cur = MagicMock()
    read_cur.fetchall.return_value = []
    read_ctx = MagicMock()
    read_ctx.__enter__.return_value = read_cur
    read_ctx.__exit__.return_value = False

    write_ctx = MagicMock()

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=[read_ctx, write_ctx]),
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        _record_closed_positions_exits(date(2026, 7, 27), MagicMock())

    # No write DatabaseContext should even be opened when there are no orphan candidates.
    write_ctx.__enter__.assert_not_called()
