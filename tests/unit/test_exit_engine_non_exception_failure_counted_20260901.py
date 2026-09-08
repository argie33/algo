#!/usr/bin/env python3
"""Regression test: a `success: False` result from executor.exit_trade() (not an exception)
must be counted in trade_errors and persisted to algo_exit_check_errors, same as a raised
exception is.

BUG FOUND 2026-09-01 (/goal session, risk-mgmt review pass): the per-trade loop's `except`
block already counts trade_errors and calls _persist_exit_check_error() for any exception
(see test_exit_engine_error_counting.py / test_exit_engine_error_audit_persistence.py), but
exit_trade() returning `{"success": False, "message": ...}` without raising - e.g. a stop-raise
rejected because the broker-side sync failed - only ever hit a bare `logger.error(...)` line.
stdout is gone the moment a scheduled/background orchestrator run exits, so a persistently-
failing stop-raise (the position keeps its prior, still-valid stop-loss, just never improves)
would recur silently every cycle with zero structured/durable record and zero reflection in
the run's error count.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


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
        "use_scale_out_targets": True,
        "execution_mode": "auto",
        "alpaca_paper_trading": False,
    }


def _trade_row(trade_id="TRD-1", symbol="AAPL", position_id="POS-1"):
    trade_date = date(2026, 7, 22) - timedelta(days=5)
    return (
        trade_id,
        symbol,
        100.0,  # entry_price
        90.0,  # stop_loss_price
        None,
        None,
        None,  # t1/t2/t3 price
        trade_date,
        position_id,
        10,  # quantity
        0,  # target_levels_hit
        95.0,  # current_stop_price (already raised once, we're trying to raise again)
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )


def _run_with_exit_trade_result(mock_config, exit_trade_result, exit_signal):
    current_date = date(2026, 7, 22)
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [_trade_row()]
    mock_cur.fetchone.return_value = ("open", 10, 95.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        engine.executor.exit_trade.return_value = exit_trade_result
        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(105.0, 100.0)),
            patch.object(engine, "_evaluate_position", return_value=exit_signal),
        ):
            result = engine.check_and_execute_exits(current_date)

    return result, mock_cur


def test_stop_raise_success_false_is_counted_and_persisted(mock_config):
    """A stop-raise (fraction=0) that returns success=False (e.g. broker-sync rejection)
    must be counted as a trade error and persisted, not just logged."""
    exit_signal = {
        "fraction": 0,
        "stage": "trailing_stop",
        "reason": "trailing stop raise",
        "new_stop": 98.0,
    }
    exit_trade_result = {
        "success": False,
        "trade_id": "TRD-1",
        "message": "Stop raise rejected: broker sync failed - simulated broker outage",
    }

    (exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price), mock_cur = (
        _run_with_exit_trade_result(mock_config, exit_trade_result, exit_signal)
    )

    assert exits_executed == 0
    assert stop_raises_executed == 0, "a failed stop-raise must not be counted as a successful one"
    assert trade_errors == 1, "a success=False result must be counted, same as a raised exception"

    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT INTO algo_exit_check_errors" in str(c)]
    assert len(insert_calls) == 1, "a success=False result must be persisted, same as a raised exception"
    args = insert_calls[0].args[1]
    assert args[1] == "TRD-1"
    assert args[2] == "POS-1"
    assert args[3] == "AAPL"
    assert args[4] == "StopRaiseFailed"
    assert "broker sync failed" in args[5]


def test_partial_exit_success_false_is_counted_and_persisted(mock_config):
    """A real exit (fraction > 0) that returns success=False must also be counted -
    same gap, different fraction value."""
    exit_signal = {
        "fraction": 0.5,
        "stage": "target_1",
        "reason": "T1 hit",
    }
    exit_trade_result = {
        "success": False,
        "trade_id": "TRD-1",
        "message": "Order rejected by broker",
    }

    (exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price), mock_cur = (
        _run_with_exit_trade_result(mock_config, exit_trade_result, exit_signal)
    )

    assert exits_executed == 0, "a failed exit must not be counted as a successful one"
    assert trade_errors == 1

    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT INTO algo_exit_check_errors" in str(c)]
    assert len(insert_calls) == 1
    args = insert_calls[0].args[1]
    assert args[4] == "ExitFailed"


def test_successful_stop_raise_is_not_counted_as_an_error(mock_config):
    """Sanity check: this fix must not turn a genuinely successful stop-raise into a
    false-positive error."""
    exit_signal = {
        "fraction": 0,
        "stage": "trailing_stop",
        "reason": "trailing stop raise",
        "new_stop": 98.0,
    }
    exit_trade_result = {
        "success": True,
        "trade_id": "TRD-1",
        "message": "Stop raised to $98.00",
    }

    (exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price), mock_cur = (
        _run_with_exit_trade_result(mock_config, exit_trade_result, exit_signal)
    )

    assert stop_raises_executed == 1
    assert trade_errors == 0
    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT INTO algo_exit_check_errors" in str(c)]
    assert len(insert_calls) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
