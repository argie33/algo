#!/usr/bin/env python3
"""Regression test for ExitEngine.check_and_execute_exits silently swallowing per-trade
exceptions without reporting them anywhere.

The per-trade loop wraps each position in a SAVEPOINT and, on any exception not matching
the recognized "symbol delisted/unavailable" case, rolls back and just logs
"Exit check failed for X" - then moves on to the next position. Previously the function
returned only a bare `exits_executed` int, so that logged failure never reached the
caller (phase6_exit_execution.run()): a live run's log showed 8 "Exit check failed"
errors alongside a Phase 6 summary of "0 errors" / status "ok". A position that errors
here gets NO exit/stop check at all this run - a real, invisible gap in risk coverage.

check_and_execute_exits() must now return (exits_executed, stop_raises_executed,
trade_errors) so the caller can surface a non-zero error count instead of reporting
false success.
"""

from datetime import date, timedelta
from decimal import Decimal
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
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def test_unexpected_per_trade_exception_is_counted_and_returned(mock_config):
    """An exception raised while evaluating one position (distinct from the handled
    delisted/404 case) must be reflected in the function's returned error count, not
    just logged and discarded."""
    current_date = date(2026, 7, 22)
    trade_date = current_date - timedelta(days=5)

    trade_row = (
        "TRD-1",  # trade_id
        "BADSYM",  # symbol
        100.0,  # entry_price
        90.0,  # stop_loss_price
        None,
        None,
        None,  # t1/t2/t3 price
        trade_date,
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        90.0,  # current_stop_price
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    # FOR UPDATE re-fetch of position status: still open, same quantity/stop
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)

        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(105.0, 100.0)),
            patch.object(
                engine,
                "_evaluate_position",
                side_effect=RuntimeError("simulated unexpected evaluation failure"),
            ),
        ):
            exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price = (
                engine.check_and_execute_exits(current_date)
            )

    assert exits_executed == 0
    assert stop_raises_executed == 0
    assert trade_errors == 1, (
        "the swallowed per-trade exception must be counted so the caller "
        "(phase6_exit_execution.run) can report a real error instead of false success"
    )
    # The savepoint must have been rolled back rather than left dangling
    rollback_calls = [c for c in mock_cur.execute.call_args_list if "ROLLBACK TO SAVEPOINT" in str(c)]
    assert len(rollback_calls) == 1


def test_no_errors_returns_zero_error_count(mock_config):
    """Sanity check: when there are no open positions, both counts are zero."""
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        with patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx):
            exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price = (
                engine.check_and_execute_exits(date(2026, 7, 22))
            )

    assert (exits_executed, stop_raises_executed, trade_errors) == (0, 0, 0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
