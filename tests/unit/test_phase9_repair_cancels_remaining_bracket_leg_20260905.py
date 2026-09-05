#!/usr/bin/env python3
"""Regression test for a 2026-09-05 real-money-readiness gap: when Phase 9 auto-repairs a
missing stop-loss leg by submitting a standalone GTC stop (order_manager_stop_repair.py),
the original bracket's take-profit leg was left untouched. If that take-profit leg was
still live (only the stop-loss leg itself had gone missing, e.g. a day-TIF expiry that hit
one leg but not the other), the position ends up with TWO unlinked live sell orders: the
still-live take-profit leg (part of Alpaca's OCO group for the ORIGINAL bracket) and the
new standalone stop (a separate order, no OCO relationship to either). If the take-profit
leg fills first, nothing cancels the standalone stop - it rests indefinitely and can later
fire against a completely unrelated future position in the same symbol.

Fix: check_and_repair_one_position() now cancels the original bracket's remaining leg(s)
via cancel_bracket_orders(alpaca_order_id) immediately after a successful standalone-stop
repair, collapsing the position to stop-only protection with no live sibling order. Done
AFTER the repair succeeds so a cancel failure here never leaves the position unprotected.
"""

from unittest.mock import MagicMock

from algo.orchestrator.phase9_stop_loss_repair import check_and_repair_one_position


def _order_mgr(cancel_result=None):
    mgr = MagicMock()
    mgr.is_order_still_live.return_value = None
    mgr.check_stop_loss_leg_live.return_value = {
        "checked": True,
        "has_live_stop_loss": False,
        "message": "No live stop-loss leg",
    }
    mgr.submit_standalone_protective_stop.return_value = {
        "success": True,
        "order_id": "new-stop-1",
        "message": "Standalone protective stop submitted",
    }
    mgr.cancel_bracket_orders.return_value = cancel_result if cancel_result is not None else {"success": True}
    return mgr


class TestRepairCancelsRemainingBracketLeg:
    def test_successful_repair_cancels_original_bracket_leg(self):
        order_mgr = _order_mgr()

        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

        assert outcome == "repaired"
        order_mgr.cancel_bracket_orders.assert_called_once()
        # Called with the ORIGINAL bracket's parent order id (from algo_trades.alpaca_order_id),
        # not the newly-submitted standalone stop's id.
        (called_order_id,), _kwargs = order_mgr.cancel_bracket_orders.call_args
        assert called_order_id != "new-stop-1"

    def test_cancel_called_after_repair_not_before(self):
        """Ordering matters: if cancel ran before the standalone stop was confirmed, a
        cancel-then-repair-fails sequence would leave the position with ZERO protection.
        Submitting first means a cancel failure only leaves the (harmless) extra leg."""
        order_mgr = _order_mgr()
        calls = []
        order_mgr.submit_standalone_protective_stop.side_effect = lambda *a, **k: (
            calls.append("submit") or {"success": True, "order_id": "new-stop-1", "message": "ok"}
        )
        order_mgr.cancel_bracket_orders.side_effect = lambda *a, **k: calls.append("cancel") or {"success": True}

        check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

        assert calls == ["submit", "cancel"]

    def test_cancel_failure_does_not_change_repaired_outcome(self):
        """A failed cancel of the remaining leg is a warning-worthy gap, not a reason to
        report the whole repair as failed - the position IS protected by the new standalone
        stop regardless of whether the stale leg was successfully cleaned up."""
        order_mgr = _order_mgr(cancel_result={"success": False, "message": "already filled"})

        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

        assert outcome == "repaired"

    def test_cancel_exception_does_not_crash_the_repair(self):
        order_mgr = _order_mgr()
        order_mgr.cancel_bracket_orders.side_effect = RuntimeError("network error")

        outcome = check_and_repair_one_position(
            order_mgr,
            pos_id=1,
            symbol="TSLA",
            trade_ids_arr=["trade-1"],
            quantity=25.0,
            current_stop_price=210.50,
            standalone_stop_order_id=None,
        )

        assert outcome == "repaired"
