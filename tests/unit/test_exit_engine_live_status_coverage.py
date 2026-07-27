#!/usr/bin/env python3
"""Regression test: ExitEngine.check_and_execute_exits' core exit-candidate query must
cover every live (non-terminal) trade status, not just 'open'/'pending'.

A real live (execution_mode="auto") order that fills writes algo_trades.status='filled' or
'partially_filled' literally (see algo/trading/executor_entry_handler.py's
_record_entry_phase: order_status = str(verified_status), passed straight through to the
INSERT) - never 'open'/'pending', which are paper-mode/review-mode-only values. The query
previously hardcoded `t.status IN ('open', 'pending')`, so a live-filled position would never
be selected for stop-loss/target/time-based exit evaluation - invisible in every prior run
because every trade recorded so far has been paper mode (status='open'). Fixed to build the
IN clause from TradeStatus.all_open().
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine
from utils.trading import TradeStatus


@pytest.fixture
def mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "auto",
        "alpaca_paper_trading": False,
    }


def test_exit_candidate_query_params_include_live_broker_statuses(mock_config):
    """The exit-candidate SELECT must be parameterized with every status in
    TradeStatus.all_open() - in particular 'filled'/'partially_filled', the literal statuses
    a real Alpaca fill is recorded with - not a hardcoded ('open', 'pending') subset."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        with patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx):
            engine.check_and_execute_exits(date(2026, 7, 22))

    candidate_calls = [c for c in mock_cur.execute.call_args_list if "algo_trades" in c.args[0]]
    assert candidate_calls, "expected the exit-candidate query (selecting from algo_trades) to be executed"
    sql_text, params = candidate_calls[0].args

    assert "algo_trades" in sql_text
    assert "filled" in params
    assert "partially_filled" in params
    for status in TradeStatus.all_open():
        assert status in params, f"expected {status!r} in exit-candidate query params, got {params!r}"
