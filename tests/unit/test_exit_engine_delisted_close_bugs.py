#!/usr/bin/env python3
"""Regression test for two bugs in ExitEngine's "price data unavailable" close-out paths
(the delisted/404 branch and the no-price-data branch in check_and_execute_exits).

Bug 1 (SQL syntax error, confirmed live against Postgres): both branches ran
`UPDATE algo_trades SET ... WHERE symbol = %s AND status = 'open' ORDER BY trade_date DESC
LIMIT 1`. PostgreSQL does not support ORDER BY/LIMIT directly on an UPDATE statement (that's
a MySQL/SQLite extension) - this raised a bare `psycopg2.errors.SyntaxError: syntax error at
or near "ORDER"` every time either branch was reached, meaning a delisted symbol or missing
price data crashed the exit loop instead of gracefully marking the position for manual
review. Fixed by moving the ORDER BY/LIMIT into a subquery that resolves the target trade_id.

Bug 2 (status mismatch): both branches hardcoded `status = 'open'` in the close UPDATE, but
the exit-candidate SELECT that surfaces trades into this loop was separately widened to
TradeStatus.all_open() (covers live 'filled'/'partially_filled' trades - see
test_exit_engine_live_status_coverage.py). A live trade selected with status='filled' would
never match `status = 'open'`, so the close UPDATE would silently affect zero rows - the
trade would stay marked 'filled' forever even though exits_executed was incremented.
"""

from datetime import date, timedelta
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


def _make_trade_row(current_date):
    trade_date = current_date - timedelta(days=5)
    return (
        "TRD-LIVE-1",  # trade_id
        "DELISTEDSYM",  # symbol
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
    )


def _run_with_fetch_recent_prices(mock_config, **fetch_kwargs):
    current_date = date(2026, 7, 22)
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [_make_trade_row(current_date)]
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
            patch.object(engine, "_fetch_recent_prices", **fetch_kwargs),
        ):
            exits_executed, trade_errors = engine.check_and_execute_exits(current_date)

    return mock_cur, exits_executed, trade_errors


def _assert_close_updates_are_valid(mock_cur):
    trade_update_calls = [
        c for c in mock_cur.execute.call_args_list if "UPDATE algo_trades" in str(c.args[0])
    ]
    position_update_calls = [
        c for c in mock_cur.execute.call_args_list if "UPDATE algo_positions" in str(c.args[0])
    ]
    assert trade_update_calls, "expected a close UPDATE against algo_trades"
    assert position_update_calls, "expected a close UPDATE against algo_positions"

    trade_sql, trade_params = trade_update_calls[0].args
    # Bug 1: ORDER BY/LIMIT must be inside a subquery, never trailing a bare UPDATE.
    assert "WHERE trade_id = (" in trade_sql, (
        "ORDER BY/LIMIT must be scoped inside a subquery - PostgreSQL rejects "
        "ORDER BY/LIMIT directly on an UPDATE statement"
    )
    # Bug 2: the close must cover every live status the candidate SELECT can surface,
    # not just 'open'.
    for status in TradeStatus.all_open():
        assert status in trade_params, f"expected {status!r} among close UPDATE params"

    position_sql, position_params = position_update_calls[0].args
    assert "status IN" in position_sql or "status = %s" in position_sql


def test_delisted_branch_close_update_is_valid_sql_and_covers_live_statuses(mock_config):
    """_fetch_recent_prices raising with "404"/"unavailable" in the message triggers the
    delisted/unavailable close-out branch."""
    mock_cur, exits_executed, trade_errors = _run_with_fetch_recent_prices(
        mock_config,
        side_effect=RuntimeError("symbol appears delisted, 404 from Alpaca"),
    )
    assert exits_executed == 1
    assert trade_errors == 0
    _assert_close_updates_are_valid(mock_cur)


def test_no_price_data_branch_close_update_is_valid_sql_and_covers_live_statuses(mock_config):
    """_fetch_recent_prices returning (None, prev_close) - as opposed to raising - triggers
    the separate "no price data" close-out branch."""
    mock_cur, exits_executed, trade_errors = _run_with_fetch_recent_prices(
        mock_config,
        return_value=(None, 95.0),
    )
    assert exits_executed == 1
    assert trade_errors == 0
    _assert_close_updates_are_valid(mock_cur)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
