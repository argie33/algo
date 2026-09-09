#!/usr/bin/env python3
"""Regression test for a 2026-09-05 real-money-readiness gap in the stop-loss auto-repair
feature (776988c4e): when Phase 9 auto-repairs a missing bracket stop-loss leg, it submits a
standalone (non-bracket) GTC protective stop and records its id in
algo_positions.standalone_stop_order_id (see order_manager_stop_repair.py /
phase9_stop_loss_repair.py). Nothing then cancelled that order when the position it protects
was later closed through the NORMAL exit path (target/time/trailing-stop) -
executor_exit_handler.py's full-exit cancellation only ever cancelled the ORIGINAL bracket by
`alpaca_order_id`, with zero awareness of a separately-tracked standalone stop.

Left uncancelled, the standalone stop rests at the broker indefinitely after the position
closes and can later fire against a completely unrelated future position opened in the same
symbol, at a stale stop price - a genuine mis-execution risk with real money.

Fix (see executor_exit_standalone_stop.py, split out for the file-size ratchet):
_execute_exit() now fetches any standalone_stop_order_id under algo_positions' own FOR
UPDATE lock and cancels it (clearing the column) alongside the bracket whenever full_exit
is True.
"""

from pathlib import Path
from unittest.mock import MagicMock

from algo.trading.executor_exit_standalone_stop import (
    cancel_standalone_stop_on_full_exit,
    fetch_standalone_stop_order_id,
)

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()


class TestFetchStandaloneStopOrderId:
    def test_returns_none_when_no_position(self):
        cur = MagicMock()

        result = fetch_standalone_stop_order_id(cur, position_id=None)

        assert result is None
        cur.execute.assert_not_called()

    def test_reads_under_for_update_lock(self):
        cur = MagicMock()
        cur.fetchone.return_value = ("standalone-order-123",)

        result = fetch_standalone_stop_order_id(cur, position_id=42)

        assert result == "standalone-order-123"
        query, params = cur.execute.call_args[0]
        assert "standalone_stop_order_id" in query
        assert "FOR UPDATE" in query
        assert params == (42,)

    def test_returns_none_when_no_prior_repair(self):
        cur = MagicMock()
        cur.fetchone.return_value = (None,)

        assert fetch_standalone_stop_order_id(cur, position_id=42) is None


class TestCancelStandaloneStopOnFullExit:
    def test_noop_when_no_standalone_stop(self):
        cancel_fn = MagicMock()
        cur = MagicMock()

        result = cancel_standalone_stop_on_full_exit(
            cancel_fn, cur, trade_id=1, position_id=1, standalone_stop_order_id=None
        )

        cancel_fn.assert_not_called()
        cur.execute.assert_not_called()
        assert result.get("filled_qty") is None

    def test_cancels_order_and_clears_column_on_success(self):
        cancel_fn = MagicMock(return_value={"success": True, "filled_qty": None, "filled_avg_price": None})
        cur = MagicMock()

        cancel_standalone_stop_on_full_exit(
            cancel_fn, cur, trade_id=1, position_id=42, standalone_stop_order_id="order-123"
        )

        cancel_fn.assert_called_once_with("order-123")
        query, params = cur.execute.call_args[0]
        assert "UPDATE algo_positions" in query
        assert "standalone_stop_order_id = NULL" in query
        assert params == (42,)

    def test_still_clears_column_when_cancel_fails(self):
        """A 422 (already terminal/filled) means the order is gone from the broker's
        perspective either way - leaving a dead id behind would make is_order_still_live()
        misreport this position as unprotected forever on a future auto-repair pass."""
        cancel_fn = MagicMock(return_value={"success": False, "message": "already filled"})
        cur = MagicMock()

        cancel_standalone_stop_on_full_exit(
            cancel_fn, cur, trade_id=1, position_id=42, standalone_stop_order_id="order-123"
        )

        cur.execute.assert_called_once()

    def test_returns_fill_info_for_caller_to_detect_a_cancel_race(self):
        """FIX (2026-09-09 real-money-readiness audit): the caller (executor_exit_handler.py)
        must be able to see filled_qty/filled_avg_price to detect a standalone stop that
        fired at the broker during this cancel request - previously this info was silently
        discarded, risking an oversell if a new full-quantity exit order was submitted on
        top of an already-executed fill."""
        cancel_fn = MagicMock(
            return_value={
                "success": False,
                "message": "already terminal - filled 50 shares before the cancel raced past it",
                "filled_qty": 50.0,
                "filled_avg_price": 12.34,
            }
        )
        cur = MagicMock()

        result = cancel_standalone_stop_on_full_exit(
            cancel_fn, cur, trade_id=1, position_id=42, standalone_stop_order_id="order-123"
        )

        assert result["filled_qty"] == 50.0
        assert result["filled_avg_price"] == 12.34


class TestExecuteExitCallsHelpersOnFullExit:
    """_execute_exit()'s full flow has a large downstream dependency graph (order
    submission, P&L, notifications) - see test_exit_handler_clears_pending_client_order_id.py
    for the established precedent of a static source check over exhaustive mocking here.
    The actual fetch/cancel logic is tested behaviorally above."""

    def test_source_wires_the_helpers_gated_on_full_exit(self):
        assert "fetch_standalone_stop_order_id" in SOURCE
        assert "cancel_standalone_stop_on_full_exit" in SOURCE
        assert "if full_exit:\n            standalone_cancel_result = cancel_standalone_stop_on_full_exit(" in SOURCE
