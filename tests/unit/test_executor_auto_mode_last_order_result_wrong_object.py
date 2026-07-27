"""Regression test: live (execution_mode="auto") order submission must not crash on the
next line after Alpaca accepts a real order.

_submit_and_validate_order() (algo/trading/executor.py) used to stash the raw OrderManager
response as self._last_order_result and the send timestamp as self._order_send_time. But this
method is wired into HandlerContext as a bound method of TradeExecutor
(HandlerContext(submit_and_validate_order_fn=self._submit_and_validate_order, ...)) - a bound
method keeps its original `self` no matter how it's later invoked, so those attributes landed
on the TradeExecutor instance. executor_entry_handler.py's EntryHandler then read them back via
self.context._last_order_result / self.context._order_send_time - self.context is the separate
HandlerContext instance, which never received either attribute.

Confirmed live 2026-07-27: in execution_mode="auto" (the system's only real live-trading mode),
every successful order submission hit AttributeError on the very next line - after Alpaca had
already accepted a real order with real money - which rolled back the same DB transaction that
would have recorded the trade/position, leaving a live, unrecorded position invisible to every
downstream stop-loss/exit/circuit-breaker check. This codebase's local dev environment only ever
runs paper mode, so this was never exercised.

Fixed by returning order_result/order_send_time explicitly through the call chain instead of
relying on shared mutable state across two different objects. This test deliberately builds a
REAL HandlerContext (not a MagicMock) - a MagicMock auto-creates any attribute accessed on it,
so a MagicMock-based test would have silently passed against the original buggy code and never
caught this exact bug class.
"""

from datetime import date as _date
from decimal import Decimal
from unittest.mock import MagicMock

from algo.trading.executor_entry_handler import EntryHandler
from algo.trading.handler_context import HandlerContext


def _make_real_context(submit_and_validate_order_fn):
    """A real HandlerContext, not a MagicMock - so undeclared-attribute access raises
    AttributeError exactly like production, instead of a Mock silently satisfying it."""
    return HandlerContext(
        config={},
        validator=MagicMock(),
        tca=MagicMock(),
        t1_target_r_multiple=2.0,
        t2_target_r_multiple=3.0,
        t3_target_r_multiple=4.0,
        execution_mode="auto",
        get_portfolio_value_fn=lambda: Decimal("100000"),
        with_cursor_fn=MagicMock(),
        validate_entry_conditions_fn=MagicMock(),
        submit_and_validate_order_fn=submit_and_validate_order_fn,
        cancel_bracket_orders_fn=MagicMock(),
        verify_order_status_fn=MagicMock(),
        get_order_filled_quantity_fn=MagicMock(),
        send_alpaca_exit_fn=MagicMock(),
        update_position_with_retry_fn=MagicMock(),
        wait_for_order_fill_fn=lambda symbol, order_id, max_wait_seconds=30: (True, 100.50, None),
    )


def test_auto_mode_successful_order_does_not_crash_on_bracket_validation():
    """The core repro: a successful auto-mode order submission must reach the bracket-leg
    check using the ACTUAL order_result returned by the order-submission call, not an
    attribute that was never set on this object."""
    order_result_dict = {
        "success": True,
        "order_id": "alpaca-order-123",
        "status": "filled",
        "executed_price": 100.50,
        "legs": [{"type": "stop"}, {"type": "limit"}],
        "order_class": "bracket",
    }

    def fake_submit_and_validate_order(*args, **kwargs):
        return (True, "alpaca-order-123", "filled", "", Decimal("100.50"), None, order_result_dict)

    context = _make_real_context(fake_submit_and_validate_order)
    handler = EntryHandler(context)
    cur = MagicMock()

    result = handler._submit_entry_phase(
        cur=cur,
        symbol="TEST",
        trade_id="TRD-TEST1",
        shares=Decimal("10"),
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("90.00"),
        target_1_price=Decimal("110.00"),
        execution_mode="auto",
        idempotency_key="idem-test-1",
    )

    order_ok, order_error, order_status, alpaca_order_id, executed_price, rejection_reason, order_send_time = result
    assert order_ok is True
    assert order_status == "filled"
    assert alpaca_order_id == "alpaca-order-123"
    assert order_send_time is not None and isinstance(order_send_time, float)


def test_auto_mode_bracket_missing_stop_leg_is_reported_not_crashed():
    """A bracket order that came back with fewer than 2 legs (missing stop-loss leg) must be
    reported as a clean failure using the real order_result, not crash trying to read it."""
    order_result_dict = {
        "success": True,
        "order_id": "alpaca-order-456",
        "status": "filled",
        "executed_price": 100.50,
        "legs": [{"type": "limit"}],  # missing the stop leg
        "order_class": "bracket",
    }

    def fake_submit_and_validate_order(*args, **kwargs):
        return (True, "alpaca-order-456", "filled", "", Decimal("100.50"), None, order_result_dict)

    context = _make_real_context(fake_submit_and_validate_order)
    handler = EntryHandler(context)
    cur = MagicMock()

    result = handler._submit_entry_phase(
        cur=cur,
        symbol="TEST",
        trade_id="TRD-TEST2",
        shares=Decimal("10"),
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("90.00"),
        target_1_price=Decimal("110.00"),
        execution_mode="auto",
        idempotency_key="idem-test-2",
    )

    order_ok = result[0]
    order_error = result[1]
    assert order_ok is False
    assert "missing stop loss leg" in order_error
