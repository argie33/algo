#!/usr/bin/env python3
"""Unit tests for executor_exit_other_leg_brackets.py's pure cancel/aggregation logic.

BUG FOUND (real-money-readiness audit): a pyramided (2+ leg) position's full-exit path
only ever cancelled trade_ids_arr[0]'s own bracket order - every OTHER leg's bracket stayed
resting live at the broker after the whole position was sold, a naked-short risk if either
later fired. See executor_exit_other_leg_brackets.py's own module docstring for full
context and algo/trading/executor_exit_handler.py's integration of these functions.
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_other_leg_brackets import (
    cancel_other_leg_brackets_on_full_exit,
    fetch_other_leg_order_ids,
)


def test_no_other_legs_is_a_clean_noop():
    """The overwhelmingly common single-leg case: nothing to cancel, no fill to report."""
    result = cancel_other_leg_brackets_on_full_exit(MagicMock(), [])
    assert result == {"success": True, "message": "No other legs", "filled_qty": None, "filled_avg_price": None}


def test_all_legs_cancel_cleanly_no_fills():
    cancel_fn = MagicMock(return_value={"success": True, "message": "cancelled"})
    result = cancel_other_leg_brackets_on_full_exit(cancel_fn, [(2, "order-2"), (3, "order-3")])

    assert cancel_fn.call_count == 2
    assert result["success"] is True
    assert result["filled_qty"] is None
    assert result["filled_avg_price"] is None


def test_one_leg_races_a_partial_fill_aggregates_qty_and_weighted_price():
    def fake_cancel(order_id):
        if order_id == "order-2":
            return {"success": True, "filled_qty": 10.0, "filled_avg_price": 100.0}
        return {"success": True, "message": "cancelled"}

    result = cancel_other_leg_brackets_on_full_exit(fake_cancel, [(2, "order-2"), (3, "order-3")])

    assert result["success"] is True
    assert result["filled_qty"] == 10.0
    assert result["filled_avg_price"] == 100.0


def test_two_legs_both_race_fills_weighted_average_price():
    def fake_cancel(order_id):
        if order_id == "order-2":
            return {"success": True, "filled_qty": 10.0, "filled_avg_price": 100.0}
        return {"success": True, "filled_qty": 20.0, "filled_avg_price": 200.0}

    result = cancel_other_leg_brackets_on_full_exit(fake_cancel, [(2, "order-2"), (3, "order-3")])

    assert result["filled_qty"] == 30.0
    # Weighted average: (10*100 + 20*200) / 30 = 500/30... wait compute: 1000+4000=5000/30=166.666...
    assert abs(result["filled_avg_price"] - (5000 / 30)) < 1e-9


def test_unconfirmed_cancel_failure_with_no_fill_reports_failure():
    """A genuine (non-race) cancel failure on another leg - the caller must treat this like
    a primary-bracket cancel failure and abort the exit in live trading."""
    cancel_fn = MagicMock(return_value={"success": False, "message": "network error"})
    result = cancel_other_leg_brackets_on_full_exit(cancel_fn, [(2, "order-2")])

    assert result["success"] is False
    assert "network error" in result["message"]
    assert result["filled_qty"] is None


def test_fill_price_missing_on_a_raced_fill_raises_rather_than_silently_dropping_it():
    cancel_fn = MagicMock(return_value={"success": True, "filled_qty": 5.0, "filled_avg_price": None})
    try:
        cancel_other_leg_brackets_on_full_exit(cancel_fn, [(2, "order-2")])
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "no fill price was available" in str(e)


def test_fetch_other_leg_order_ids_excludes_primary_and_null_orders():
    cur = MagicMock()
    cur.fetchall.return_value = [(2, "order-2"), (3, "order-3")]

    result = fetch_other_leg_order_ids(cur, position_id=99, primary_trade_id=1)

    assert result == [(2, "order-2"), (3, "order-3")]
    sql, params = cur.execute.call_args[0]
    assert params == (99, 1)
    assert "trade_id != %s" in sql
    assert "alpaca_order_id IS NOT NULL" in sql


def test_fetch_other_leg_order_ids_no_position_returns_empty():
    cur = MagicMock()
    assert fetch_other_leg_order_ids(cur, position_id=None, primary_trade_id=1) == []
    cur.execute.assert_not_called()
