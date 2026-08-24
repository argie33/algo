#!/usr/bin/env python3
"""Regression test for the 2026-08-24 broker-stop-sync fix.

/goal session: user asked whether the algo's order types/stop-loss handling followed
best practice. Investigation found that order_manager.send_bracket_order() submits a
real Alpaca bracket order at entry (broker-enforced stop-loss leg, live even if our
code never runs again) - but every later "raise the stop" decision (breakeven move,
chandelier trail, position_monitor.py's trailing-stop recommendation) only updated
algo_positions.current_stop_price in our own database. Nothing ever pushed the
improved stop back to the resting broker order, so the "trailed stop" was purely a
belief in our own DB: the position stayed protected only at the wider, stale
entry-time level until the next orchestrator run happened to notice a breach itself.

Fixed by adding OrderManager.sync_bracket_stop_loss() (fetches the bracket's live
stop-loss leg via GET /v2/orders/{parent_id} and PATCHes its stop_price) and wiring it
into executor_exit_handler.py's ExitHandler._raise_stop_only() - called BEFORE the DB
write, fail-closed: if the broker sync doesn't succeed, current_stop_price is not
updated, so our own system's belief about protection can never get ahead of what's
actually resting at the exchange.
"""

from unittest.mock import MagicMock

import pytest

from algo.trading.executor_exit_handler import ExitHandler


def _make_context(sync_result):
    context = MagicMock()
    context._sync_bracket_stop_loss = MagicMock(return_value=sync_result)
    return context


def _make_cursor(existing_stop_price, alpaca_order_id, quantity=10.0, rowcount=1):
    cur = MagicMock()
    cur.fetchone.return_value = (existing_stop_price, alpaca_order_id, quantity)
    cur.rowcount = rowcount
    return cur


class TestRaiseStopSyncsBrokerBeforeDbWrite:
    def test_broker_sync_called_with_alpaca_order_id_and_new_stop(self):
        context = _make_context({"success": True, "synced": True, "message": "ok"})
        cur = _make_cursor(existing_stop_price=100.0, alpaca_order_id="alpaca-abc-123")
        handler = ExitHandler(context)

        result = handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        context._sync_bracket_stop_loss.assert_called_once_with("alpaca-abc-123", 105.0, 10.0)
        assert result["success"] is True

    def test_db_not_updated_when_broker_sync_fails(self):
        """Fail closed: if we can't confirm the broker's resting stop moved, don't tell
        our own system it did - the UPDATE must never execute."""
        context = _make_context({"success": False, "synced": False, "message": "No live stop-loss leg found"})
        cur = _make_cursor(existing_stop_price=100.0, alpaca_order_id="alpaca-abc-123")
        handler = ExitHandler(context)

        result = handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        assert result["success"] is False
        assert "broker sync failed" in result["message"]
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in str(c)]
        assert not update_calls, "current_stop_price UPDATE must not run when broker sync fails"

    def test_db_updated_when_broker_sync_succeeds(self):
        context = _make_context({"success": True, "synced": True, "message": "ok"})
        cur = _make_cursor(existing_stop_price=100.0, alpaca_order_id="alpaca-abc-123")
        handler = ExitHandler(context)

        handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in str(c)]
        assert update_calls, "current_stop_price UPDATE must run once broker sync succeeds"

    def test_paper_local_order_treated_as_success_no_broker_call_needed(self):
        """sync_bracket_stop_loss itself returns success=True/synced=False for LOCAL-/
        PENDING- orders (nothing at the broker to sync) - the DB update must still
        proceed in that case, same as every other broker-optional path."""
        context = _make_context({"success": True, "synced": False, "message": "paper mode"})
        cur = _make_cursor(existing_stop_price=100.0, alpaca_order_id="LOCAL-abc")
        handler = ExitHandler(context)

        result = handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=105.0,
            cur=cur,
        )

        assert result["success"] is True
        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in str(c)]
        assert update_calls

    def test_broker_sync_not_attempted_when_new_stop_not_above_existing(self):
        """The existing 'not above existing stop' rejection must short-circuit before
        any broker call - no reason to touch the broker for a rejected no-op raise."""
        context = _make_context({"success": True, "synced": True, "message": "ok"})
        cur = _make_cursor(existing_stop_price=100.0, alpaca_order_id="alpaca-abc-123")
        handler = ExitHandler(context)

        result = handler.execute_exit(
            trade_id=42,
            exit_price=None,
            exit_reason="trailing stop tighten",
            exit_fraction=0,
            exit_stage="trail",
            new_stop_price=99.0,  # not above existing 100.0
            cur=cur,
        )

        assert result["success"] is False
        context._sync_bracket_stop_loss.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
