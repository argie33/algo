"""Regression test: a bracket-cancel failure during fill-timeout cleanup must not crash the
entry pipeline for that symbol - it must be logged as a warning and the fill failure still
reported normally.

BUG FOUND 2026-08-31 (recovered from a stranded branch onto main 2026-09-01, /goal session -
see risk_min_weight_available_floor_added_20260831 memory entry for the broader pattern):
`order_manager.cancel_bracket_orders()` raises a plain `RuntimeError` on every real failure path
(a non-retryable Alpaca status - e.g. the order already filled and can no longer be cancelled -
or 429/503 retries exhausted; see that method's own comment: "a failed cancel leaves a real
resting bracket order at the broker with no matching DB record, exactly the orphaned-position
class AlpacaSyncManager._sync_untracked_positions exists to catch later").
`executor_entry_handler.py`'s three call sites around `self.context._cancel_bracket_orders(...)`
each wrapped that call in `except (OrderExecutionError, DatabaseError, requests.RequestException,
requests.Timeout)` - none of which is `RuntimeError` or a supertype of it (`OrderExecutionError`/
`DatabaseError` are unrelated `TradingError` subclasses). The intended "log a warning, still
report the fill failure" behavior could never actually trigger for a real cancel failure - the
RuntimeError propagated uncaught out of `_submit_entry_phase` instead. Fixed by adding
`RuntimeError` to all three except tuples.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor_entry_handler import EntryHandler


def _make_handler():
    handler_context = MagicMock()
    handler_context._submit_and_validate_order.return_value = (
        True,  # order_ok
        "alpaca-order-123",  # alpaca_order_id
        "new",  # order_status (immediate POST response)
        "",  # order_error
        None,  # executed_price (not yet filled)
        None,  # rejection_reason
        {"legs": [{"order_type": "stop"}, {"order_type": "limit"}], "order_class": "bracket"},
    )
    return EntryHandler(handler_context), handler_context


def test_cancel_bracket_runtime_error_is_caught_not_propagated():
    """A cancel failure (real RuntimeError from cancel_bracket_orders) during fill-timeout
    cleanup must be swallowed with a warning, not crash _submit_entry_phase - the fill-timeout
    failure must still be returned normally to the caller."""
    handler, handler_context = _make_handler()
    handler_context._wait_for_order_fill.return_value = (
        False,
        None,
        "Order fill timeout after 30.0s (60 polls). Order may still fill asynchronously.",
    )
    handler_context._cancel_bracket_orders.side_effect = RuntimeError(
        "[CANCEL_BRACKET] Failed to cancel order alpaca-order-123 after 3 attempts: Failed to cancel: 422"
    )

    with patch("algo.trading.executor_entry_handler.notify"):
        result = handler._submit_entry_phase(
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

    order_ok, fill_error = result[0], result[1]
    assert order_ok is False
    assert "timeout" in fill_error.lower()
    handler_context._cancel_bracket_orders.assert_called_once_with("alpaca-order-123")
