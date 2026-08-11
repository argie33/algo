#!/usr/bin/env python3
"""Regression test: a NaN/Infinity entry_price, init_stop, active_stop, or cur_price must
be isolated to the one bad position (counted as a trade_error, savepoint rolled back), not
propagate out of check_and_execute_exits() and abort exit evaluation - including hard
stop-loss checks - for every OTHER open position in the same run.

BUG FOUND 2026-08-11: entry_price/init_stop/active_stop were converted to Decimal but never
checked for NaN/Infinity, and cur_price/prev_close (from a live quote or DB fallback) were
never checked either. Decimal arithmetic silently propagates NaN (unlike ordering
comparisons, which raise) - a NaN value here would reach a hard-stop comparison like
`cur_price_dec <= hard_stop_dec` and raise a raw decimal.InvalidOperation (an
ArithmeticError). check_and_execute_exits()'s own per-position `except` clause only catches
(psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, KeyError, RuntimeError) -
InvalidOperation isn't in that list, so pre-fix this would propagate straight out of the
per-position try, aborting the whole batch instead of being counted as one bad position's
trade_error like every other data-quality problem this loop handles.
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
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _make_trade_row(symbol, entry_price, stop_loss_price, trade_date, t1=None, t2=None, t3=None):
    return (
        "TRD-1",  # trade_id
        symbol,
        entry_price,
        stop_loss_price,
        t1,
        t2,
        t3,  # t1/t2/t3 price
        trade_date,
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        stop_loss_price,  # current_stop_price
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )


def _run_with_mocks(mock_config, trade_row, current_date, fetch_recent_prices_return=(105.0, 100.0)):
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    mock_cur.fetchone.return_value = ("open", 10, trade_row[3])

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=fetch_recent_prices_return),
        ):
            result = engine.check_and_execute_exits(current_date)
    return result, mock_cur


class TestNanPriceIsolatesOnePosition:
    def test_nan_entry_price_counted_as_trade_error_not_uncaught_raise(self, mock_config):
        current_date = date(2026, 7, 22)
        trade_date = current_date - timedelta(days=5)
        trade_row = _make_trade_row("BADSYM", float("nan"), 90.0, trade_date)

        (exits_executed, stop_raises_executed, trade_errors, _forced), mock_cur = _run_with_mocks(
            mock_config, trade_row, current_date
        )

        assert trade_errors == 1, (
            "a NaN entry_price must be caught and counted as this position's trade_error, "
            "not raise decimal.InvalidOperation out of the whole batch"
        )
        assert exits_executed == 0
        rollback_calls = [c for c in mock_cur.execute.call_args_list if "ROLLBACK TO SAVEPOINT" in str(c)]
        assert len(rollback_calls) == 1

    def test_nan_init_stop_counted_as_trade_error(self, mock_config):
        current_date = date(2026, 7, 22)
        trade_date = current_date - timedelta(days=5)
        trade_row = _make_trade_row("BADSYM", 100.0, float("nan"), trade_date)

        (exits_executed, stop_raises_executed, trade_errors, _forced), _mock_cur = _run_with_mocks(
            mock_config, trade_row, current_date
        )

        assert trade_errors == 1
        assert exits_executed == 0

    def test_nan_cur_price_counted_as_trade_error(self, mock_config):
        current_date = date(2026, 7, 22)
        trade_date = current_date - timedelta(days=5)
        trade_row = _make_trade_row("BADSYM", 100.0, 90.0, trade_date)

        (exits_executed, stop_raises_executed, trade_errors, _forced), _mock_cur = _run_with_mocks(
            mock_config, trade_row, current_date, fetch_recent_prices_return=(float("nan"), 100.0)
        )

        assert trade_errors == 1, "a NaN cur_price (live quote) must isolate this position, not abort the batch"
        assert exits_executed == 0

    def test_valid_prices_still_process_normally(self, mock_config):
        """Sanity check: the fix must not break the normal (finite, valid) path."""
        current_date = date(2026, 7, 22)
        trade_date = current_date - timedelta(days=5)
        trade_row = _make_trade_row("GOODSYM", 100.0, 90.0, trade_date, t1=110.0, t2=120.0, t3=130.0)

        (exits_executed, stop_raises_executed, trade_errors, _forced), _mock_cur = _run_with_mocks(
            mock_config, trade_row, current_date, fetch_recent_prices_return=(105.0, 100.0)
        )

        assert trade_errors == 0
