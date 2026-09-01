#!/usr/bin/env python3
"""Regression test: phase9_reconciliation._record_closed_positions_exits must reject a NULL
algo_trades.stop_loss_price and a non-positive position_qty explicitly, not let them reach
`float(entry_price) - float(stop_loss_price)` / Decimal P&L math unguarded.

Unlike algo_positions.stop_loss_price (NOT NULL since migration 020), algo_trades.stop_loss_price
has no such constraint - migration 035's own `WHERE stop_loss_price IS NOT NULL` filter on this
same table confirms it happens in practice, not just in theory. Before this fix, a NULL value here
reached risk_per_share = float(entry_price) - float(stop_loss_price) and raised an uncaught
TypeError - not a psycopg2 error, so this function's `except (psycopg2.DatabaseError,
psycopg2.OperationalError)` handlers never saw it, and it occurred before the per-symbol SAVEPOINT
was even created. That TypeError would propagate out of the whole `with DatabaseContext("write")`
block, which rolls back on ANY exception - silently discarding every OTHER symbol already
successfully recorded earlier in the same batch, not just the one bad row. Found during a
same-day Phase 9 deep-review pass, verified against the actual migration history before fixing.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def _make_read_cursor(rows):
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = rows
    return cur


def test_null_stop_loss_price_raises_before_any_write():
    # Query returns: symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity, trade_id, current_price
    closed_row = ("AAPL", 150.0, 10, None, 10, 123, 148.0)
    read_cur = _make_read_cursor([closed_row])
    write_cur = MagicMock()

    def fake_log(*args, **kwargs):
        pass

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
        patch("algo.reporting.notify"),
    ):
        mock_ctx.return_value.__enter__.side_effect = [read_cur, write_cur]
        mock_ctx.return_value.__exit__.return_value = False

        with pytest.raises(RuntimeError, match="stop_loss_price"):
            _record_closed_positions_exits({}, run_date=None, log_phase_result_fn=fake_log)

    # Must fail before ever touching algo_trades/algo_positions - no partial/garbage write.
    update_calls = [c for c in write_cur.execute.call_args_list if c.args and "UPDATE" in str(c.args[0])]
    assert not update_calls, "must reject the row before issuing any UPDATE"


def test_zero_position_qty_raises_before_any_write():
    closed_row = ("AAPL", 150.0, 0, 145.0, 10, 123, 148.0)
    read_cur = _make_read_cursor([closed_row])
    write_cur = MagicMock()

    def fake_log(*args, **kwargs):
        pass

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
        patch("algo.reporting.notify"),
    ):
        mock_ctx.return_value.__enter__.side_effect = [read_cur, write_cur]
        mock_ctx.return_value.__exit__.return_value = False

        with pytest.raises(RuntimeError, match="position_qty"):
            _record_closed_positions_exits({}, run_date=None, log_phase_result_fn=fake_log)

    update_calls = [c for c in write_cur.execute.call_args_list if c.args and "UPDATE" in str(c.args[0])]
    assert not update_calls, "must reject the row before issuing any UPDATE"


def test_valid_row_with_populated_stop_loss_price_still_passes_through(monkeypatch):
    # Confirms the new guards don't false-positive on the ordinary, already-covered happy path
    # from test_phase9_exit_recording_db_failure.py's rowcount==0 case.
    closed_row = ("AAPL", 150.0, 10, 145.0, 10, 123, 148.0)
    read_cur = _make_read_cursor([closed_row])
    write_cur = MagicMock()

    def execute_side_effect(sql, params=None):
        if "UPDATE algo_trades" in sql and "exit_date" in sql:
            write_cur.rowcount = 1
        elif "UPDATE algo_trades" in sql and "verify" not in sql.lower():
            pass
        elif "UPDATE algo_positions" in sql:
            write_cur.rowcount = 1
        return None

    write_cur.execute.side_effect = execute_side_effect
    write_cur.fetchone.side_effect = [
        (150.50,),  # price_daily close
        (0,),  # prior_partial audit_log sum
        (150.50,),  # exit_price verification SELECT after UPDATE
    ]

    def fake_log(*args, **kwargs):
        pass

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx,
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        mock_ctx.return_value.__enter__.side_effect = [read_cur, write_cur]
        mock_ctx.return_value.__exit__.return_value = False

        _record_closed_positions_exits({}, run_date=None, log_phase_result_fn=fake_log)

    update_calls = [c for c in write_cur.execute.call_args_list if c.args and "UPDATE" in str(c.args[0])]
    assert update_calls, "a valid row must still reach the UPDATE statements"
