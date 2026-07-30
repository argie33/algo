#!/usr/bin/env python3
"""Regression test: Phase 9's orphan-position-close path (_record_closed_positions_exits)
must set algo_trades.exit_time, not just exit_date.

This is one of three close paths (alongside exit_engine.py's delisted/no-price-data
branches) that closed a trade without setting exit_time - unlike
executor_exit_handler.py's normal exit path, which always sets it. Since
algo_trades.exit_time was mostly NULL as a result, circuit_breaker.py's
_check_consecutive_losses/_check_win_rate_floor "most recent N exits" ordering (which
sorts by exit_time) was effectively non-deterministic on same-exit_date trades. Fixing
just the circuit breaker ordering wasn't enough without also fixing the paths that leave
exit_time NULL in the first place.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _record_closed_positions_exits


def test_orphan_close_sets_exit_time_not_just_exit_date():
    mock_read_cur = MagicMock()
    # Query returns: symbol, avg_entry_price, quantity, stop_loss_price, entry_quantity
    mock_read_cur.fetchall.return_value = [("AAPL", 100.0, 10, 95.0, 10)]
    mock_read_ctx = MagicMock()
    mock_read_ctx.__enter__.return_value = mock_read_cur
    mock_read_ctx.__exit__.return_value = False

    mock_write_cur = MagicMock()
    mock_write_cur.rowcount = 1
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
        _record_closed_positions_exits(date(2026, 7, 24), MagicMock())

    trade_update_calls = [
        c for c in mock_write_cur.execute.call_args_list if "UPDATE algo_trades" in str(c.args[0])
    ]
    assert trade_update_calls, "expected an UPDATE algo_trades call for the orphan-close path"
    sql_text = trade_update_calls[0].args[0]
    assert "exit_time = CURRENT_TIMESTAMP" in sql_text
