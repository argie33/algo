"""Regression test: once Phase 9 auto-repairs a position onto a STANDALONE protective stop
(the original bracket's stop-loss leg is gone, cancelled - see phase9_stop_loss_repair.py),
ExitHandler._raise_stop_only used to call sync_bracket_stop_loss unconditionally with the
original (now-dead) bracket's alpaca_order_id. That call can never succeed once the bracket
leg is gone, so every future trailing-stop improvement (breakeven move, chandelier trail) for
such a position was a permanent silent no-op forever after its first Phase 9 repair -
current_stop_price never advances and the broker-side stop never trails.

Found 2026-09-05 (real-money-readiness order-execution audit). Fixed by routing to
OrderManager.sync_standalone_stop instead when algo_positions.standalone_stop_order_id is set,
and re-persisting the new order id on success (Alpaca replaces orders via cancel-and-recreate).
"""

from unittest.mock import MagicMock

from algo.trading.executor_exit_handler import ExitHandler


def _make_context(**overrides):
    context = MagicMock()
    context._sync_bracket_stop_loss = MagicMock()
    context._sync_standalone_stop = MagicMock()
    for k, v in overrides.items():
        setattr(context, k, v)
    return context


def _make_cursor(existing_stop_price, alpaca_order_id, quantity, standalone_stop_order_id, position_id="pos-1"):
    cur = MagicMock()
    cur.fetchone.return_value = (existing_stop_price, alpaca_order_id, quantity, standalone_stop_order_id, position_id)
    cur.rowcount = 1
    return cur


def test_standalone_stop_present_routes_to_sync_standalone_not_bracket():
    context = _make_context()
    context._sync_standalone_stop.return_value = {"success": True, "synced": True, "message": "ok"}
    cur = _make_cursor(
        existing_stop_price=100.0,
        alpaca_order_id="dead-bracket-order",
        quantity=10.0,
        standalone_stop_order_id="standalone-stop-1",
    )
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

    context._sync_standalone_stop.assert_called_once_with("standalone-stop-1", 105.0, 10.0)
    context._sync_bracket_stop_loss.assert_not_called()
    assert result["success"] is True


def test_standalone_stop_replacement_persists_new_order_id():
    """Alpaca implements order replacement as cancel-and-recreate - the new id must be
    re-persisted or the next liveness check looks up a now-terminal order id and believes
    protection is gone."""
    context = _make_context()
    context._sync_standalone_stop.return_value = {
        "success": True,
        "synced": True,
        "new_order_id": "standalone-stop-2",
        "message": "ok",
    }
    cur = _make_cursor(
        existing_stop_price=100.0,
        alpaca_order_id="dead-bracket-order",
        quantity=10.0,
        standalone_stop_order_id="standalone-stop-1",
        position_id="pos-99",
    )
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

    persist_calls = [
        c
        for c in cur.execute.call_args_list
        if "standalone_stop_order_id" in str(c) and "UPDATE algo_positions" in str(c)
    ]
    assert persist_calls, "new standalone stop order id must be re-persisted"
    assert persist_calls[0].args[1] == ("standalone-stop-2", "pos-99")


def test_no_standalone_stop_still_uses_bracket_sync():
    """No regression for the common case - a position still on its original bracket must
    keep using sync_bracket_stop_loss exactly as before."""
    context = _make_context()
    context._sync_bracket_stop_loss.return_value = {"success": True, "synced": True, "message": "ok"}
    cur = _make_cursor(
        existing_stop_price=100.0,
        alpaca_order_id="alpaca-abc-123",
        quantity=10.0,
        standalone_stop_order_id=None,
    )
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
    context._sync_standalone_stop.assert_not_called()
    assert result["success"] is True


def test_standalone_stop_sync_failure_fails_closed():
    context = _make_context()
    context._sync_standalone_stop.return_value = {"success": False, "message": "broker unreachable"}
    cur = _make_cursor(
        existing_stop_price=100.0,
        alpaca_order_id="dead-bracket-order",
        quantity=10.0,
        standalone_stop_order_id="standalone-stop-1",
    )
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
    update_calls = [c for c in cur.execute.call_args_list if "SET current_stop_price" in str(c)]
    assert not update_calls
