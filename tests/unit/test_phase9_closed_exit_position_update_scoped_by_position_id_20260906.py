"""Regression test: _record_closed_positions_exits()'s UPDATE algo_positions used to be
scoped by `symbol` alone (real-money-readiness audit, 2026-09-06). algo_positions has no
DB-level unique constraint on symbol (only on position_id) - application-level dedup is the
only thing preventing two open positions for the same symbol - so a symbol-only UPDATE here
could close/misattribute the wrong position in that rare race. Fixed to thread ap.position_id
through the query and scope the UPDATE by it whenever available, falling back to symbol-only
only for legacy rows with no position_id.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def _run(closed_row):
    mock_read_cur = MagicMock()
    mock_read_cur.fetchall.return_value = [closed_row]
    mock_read_ctx = MagicMock()
    mock_read_ctx.__enter__.return_value = mock_read_cur
    mock_read_ctx.__exit__.return_value = False

    mock_write_cur = MagicMock()
    mock_write_cur.rowcount = 1
    mock_write_cur.fetchone.side_effect = [
        (150.0,),  # price_daily close price
        (0,),  # COALESCE(SUM(prior_partial), 0)
        (150.0,),  # verify exit_price was written
    ]
    mock_write_ctx = MagicMock()
    mock_write_ctx.__enter__.return_value = mock_write_cur
    mock_write_ctx.__exit__.return_value = False

    ctx_instances = [mock_read_ctx, mock_write_ctx]

    def fake_database_context(role):
        return ctx_instances.pop(0)

    with (
        patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", side_effect=fake_database_context),
        patch("algo.orchestrator.phase9_reconciliation.acquire_advisory_lock"),
        patch("algo.orchestrator.phase9_reconciliation.release_advisory_lock"),
    ):
        _record_closed_positions_exits({}, date(2026, 7, 24), MagicMock())

    return mock_write_cur


def test_position_update_scoped_by_position_id_when_available():
    closed_row = ("AAPL", 100.0, 10, 95.0, 10, 456, 98.0, "POS-123")
    write_cur = _run(closed_row)

    position_updates = [c for c in write_cur.execute.call_args_list if "UPDATE algo_positions" in str(c.args[0])]
    assert len(position_updates) == 1
    sql, params = position_updates[0].args
    assert "WHERE position_id = %s AND status = 'open'" in sql
    assert params[-1] == "POS-123"


def test_position_update_falls_back_to_symbol_when_no_position_id():
    closed_row = ("AAPL", 100.0, 10, 95.0, 10, 456, 98.0, None)
    write_cur = _run(closed_row)

    position_updates = [c for c in write_cur.execute.call_args_list if "UPDATE algo_positions" in str(c.args[0])]
    assert len(position_updates) == 1
    sql, params = position_updates[0].args
    assert "WHERE symbol = %s AND status = 'open'" in sql
    assert params[-1] == "AAPL"
