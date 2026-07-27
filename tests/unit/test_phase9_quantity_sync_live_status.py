#!/usr/bin/env python3
"""Regression test: Phase 9's quantity-sync step must cover every live (non-terminal)
trade status, not just 'open'.

A real live (execution_mode="auto") order that fills writes algo_trades.status='filled'
or 'partially_filled' literally (see algo/trading/executor_entry_handler.py's
_record_entry_phase) - never 'open', which is a paper-mode-only value. The query
previously hardcoded `status = 'open'`, so a live-filled trade's quantity column would
never be synced from entry_quantity - invisible in every prior run because every trade
recorded so far has been paper mode (status='open'). Fixed to build the WHERE clause
from TradeStatus.all_open().
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase9_reconciliation import _sync_position_quantities_step
from utils.trading import TradeStatus


def test_quantity_sync_query_params_include_live_broker_statuses():
    """The quantity-sync UPDATE must be parameterized with every status in
    TradeStatus.all_open() - in particular 'filled'/'partially_filled', the literal
    statuses a real Alpaca fill is recorded with - not just 'open'."""
    mock_cur = MagicMock()
    mock_cur.rowcount = 0

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    log_calls = []

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext", return_value=mock_ctx):
        _sync_position_quantities_step(lambda *args: log_calls.append(args))

    assert mock_cur.execute.call_args_list, "expected the quantity-sync UPDATE to be executed"
    sql_text, params = mock_cur.execute.call_args_list[0].args

    assert "algo_trades" in sql_text
    assert "filled" in params
    assert "partially_filled" in params
    for status in TradeStatus.all_open():
        assert status in params, f"expected {status!r} in quantity-sync query params, got {params!r}"

    assert log_calls and log_calls[0][:3] == (9, "quantity_sync", "success")
