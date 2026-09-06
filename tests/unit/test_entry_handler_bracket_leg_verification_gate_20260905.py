"""Regression test for the bracket-leg-verification gate in `_submit_entry_phase`
(executor_entry_handler.py, ~lines 892-972) - real-money-readiness audit (2026-09-05) flagged
this as the single most load-bearing check in the entry path (it is what prevents a position
from ever being considered "live" without a broker-side stop-loss attached) with zero direct
regression test coverage. This closes that gap.

Covers: too few legs, a stop-only bracket (missing take_profit), a limit-only bracket (missing
stop_loss), and the pass-through case where both legs are present (must NOT be rejected by this
gate - reaches the subsequent fill-wait call instead).
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler(order_result):
    handler_context = MagicMock()
    handler_context._submit_and_validate_order.return_value = (
        True,  # order_ok
        "alpaca-order-123",  # alpaca_order_id
        "new",  # order_status
        "",  # order_error
        None,  # executed_price
        None,  # rejection_reason
        order_result,
    )
    return EntryHandler(handler_context), handler_context


def _submit(handler):
    return handler._submit_entry_phase(
        cur=MagicMock(),
        symbol="TESTSYM",
        trade_id="trade-1",
        shares=Decimal("10"),
        entry_price=Decimal("100.00"),
        stop_loss_price=Decimal("95.00"),
        target_1_price=Decimal("110.00"),
        execution_mode="auto",
        idempotency_key="a" * 64,
    )


def test_too_few_legs_rejected_and_bracket_cancelled():
    handler, handler_context = _make_handler({"legs": [{"order_type": "stop"}], "order_class": "bracket"})

    with patch("algo.trading.executor_entry_handler.notify"):
        result = _submit(handler)

    order_ok, order_error = result[0], result[1]
    assert order_ok is False
    assert "missing stop loss leg" in order_error.lower()
    handler_context._cancel_bracket_orders.assert_called_once_with("alpaca-order-123")
    handler_context._wait_for_order_fill.assert_not_called()


def test_missing_stop_loss_leg_rejected_and_bracket_cancelled():
    handler, handler_context = _make_handler(
        {"legs": [{"order_type": "limit"}, {"order_type": "limit"}], "order_class": "bracket"}
    )

    with patch("algo.trading.executor_entry_handler.notify"):
        result = _submit(handler)

    order_ok, order_error = result[0], result[1]
    assert order_ok is False
    assert "stop_loss" in order_error
    assert "take_profit" not in order_error
    handler_context._cancel_bracket_orders.assert_called_once_with("alpaca-order-123")
    handler_context._wait_for_order_fill.assert_not_called()


def test_missing_take_profit_leg_rejected_and_bracket_cancelled():
    handler, handler_context = _make_handler(
        {"legs": [{"order_type": "stop"}, {"order_type": "stop"}], "order_class": "bracket"}
    )

    with patch("algo.trading.executor_entry_handler.notify"):
        result = _submit(handler)

    order_ok, order_error = result[0], result[1]
    assert order_ok is False
    assert "take_profit" in order_error
    assert "stop_loss" not in order_error
    handler_context._cancel_bracket_orders.assert_called_once_with("alpaca-order-123")
    handler_context._wait_for_order_fill.assert_not_called()


def test_complete_bracket_passes_gate_and_proceeds_to_fill_wait():
    handler, handler_context = _make_handler(
        {"legs": [{"order_type": "stop"}, {"order_type": "limit"}], "order_class": "bracket"}
    )
    handler_context._wait_for_order_fill.return_value = (
        True,
        Decimal("100.00"),
        "",
    )

    with patch("algo.trading.executor_entry_handler.notify"):
        _submit(handler)

    handler_context._cancel_bracket_orders.assert_not_called()
    handler_context._wait_for_order_fill.assert_called_once()
