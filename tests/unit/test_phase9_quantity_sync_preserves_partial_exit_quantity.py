#!/usr/bin/env python3
"""Regression test: Phase 9's quantity-backfill step must only fill in a NULL quantity,
never overwrite a quantity that legitimately differs from entry_quantity because of a
partial exit.

CRITICAL (goal session, "before real money" finance-accuracy audit): this step used to
run `UPDATE algo_trades SET quantity = entry_quantity WHERE ... (quantity IS NULL OR
quantity != entry_quantity)` - treating ANY mismatch as drift to correct. But a partial
exit legitimately reduces algo_trades.quantity below entry_quantity (see
executor_exit_handler.py's partial-exit UPDATE), and this step runs every orchestrator
cycle - it was silently resetting a correctly-reduced quantity back to the full original
size on the very next run, every time. Live-reproduced via TRD-29F350E6A9 (RPM): see
test_executor_exit_handler_partial_exit_updates_quantity.py for the write-side half of
this same fix.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _sync_position_quantities_step


def _run_and_capture_update_sql():
    mock_cur = MagicMock()
    mock_cur.rowcount = 0
    mock_cur.fetchone.return_value = (0, None)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
        _sync_position_quantities_step(lambda *args: None)

    update_call = next(c for c in mock_cur.execute.call_args_list if "UPDATE algo_trades" in c.args[0])
    return update_call.args[0]


def test_quantity_sync_only_backfills_null_not_legitimate_mismatches():
    sql_text = _run_and_capture_update_sql()

    assert "quantity IS NULL" in sql_text
    assert "quantity != entry_quantity" not in sql_text, (
        "the quantity-sync UPDATE must not treat quantity != entry_quantity as drift to "
        "correct - a partial exit legitimately produces that exact mismatch, and this "
        "step running every orchestrator cycle would silently undo it, corrupting "
        "algo_positions.quantity (via position_sync.py's SUM) and risking an over-sell "
        "of already-exited shares in live/auto mode"
    )


def test_pre_update_validation_also_scoped_to_null_quantity():
    """The pre-update entry_quantity validation must be scoped the same way - it should
    not raise/abort the whole sync because of an unrelated trade whose quantity is
    already correctly set (e.g. reduced by a partial exit) but happens to have some
    other entry_quantity data issue outside this function's concern."""
    mock_cur = MagicMock()
    mock_cur.rowcount = 0
    mock_cur.fetchone.return_value = (0, None)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
        _sync_position_quantities_step(lambda *args: None)

    validation_call = mock_cur.execute.call_args_list[0]
    assert "quantity IS NULL" in validation_call.args[0]
