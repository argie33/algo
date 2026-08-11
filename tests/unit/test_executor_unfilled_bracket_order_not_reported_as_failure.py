"""Regression test: a live (execution_mode="auto") bracket order that Alpaca ACCEPTS but
has not yet FILLED must not be reported as a submission failure.

algo/trading/order_manager.py's send_bracket_order() always submits a LIMIT order
(order_data["type"]="limit") - Alpaca's immediate POST /v2/orders response for a limit
order commonly comes back status="new"/"accepted"/"pending_new" with
filled_avg_price=null, since the order hasn't matched yet. This is normal, expected
behavior, not a failure - order_manager.py's own wait_for_order_fill() explicitly treats
those same statuses as "still waiting" and polls until a real fill (or a genuine terminal
failure/timeout).

But TradeExecutor._submit_and_validate_order() (algo/trading/executor.py) used to require
executed_price to be non-None immediately after send_bracket_order() returned, raising
OrderExecutionError otherwise. executor_entry_handler.py's _submit_entry_phase() treats
that OrderExecutionError identically to a genuine rejection (order_ok=False) and returns
immediately - BEFORE ever reaching its own wait_for_order_fill() polling step that's
specifically designed to resolve the real fill price for exactly this case.

Net effect in execution_mode="auto": Alpaca accepts a real bracket order (live at the
broker, stop-loss/take-profit legs attached, real money at risk) and the system reports
the submission as FAILED and never creates a trade/position record - the same "invisible
live position" danger class as the 2026-07-27 AttributeError incident (see
test_executor_auto_mode_last_order_result_wrong_object.py), reached via a different path.

This test builds a REAL OrderManager (not a mock) and mocks only requests.post to return
a realistic Alpaca "order accepted, not yet filled" response - exercising the actual
send_bracket_order() -> AlpacaResponseValidator -> _submit_and_validate_order() chain,
not just a hand-built fake return value.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.trading.executor import TradeExecutor
from algo.trading.order_manager import OrderManager


def _unfilled_alpaca_response(order_id: str = "alpaca-order-789") -> dict:
    """A realistic Alpaca order object for a bracket LIMIT order that has just been
    accepted but has NOT filled yet - filled_avg_price is null, status is "new"."""
    return {
        "id": order_id,
        "client_order_id": "idem-test-unfilled",
        "status": "new",
        "filled_avg_price": None,
        "order_class": "bracket",
        "legs": [
            {"order_type": "stop", "order_side": "sell"},
            {"order_type": "limit", "order_side": "sell"},
        ],
    }


def _make_bound_submit_and_validate_order(order_manager: OrderManager):
    """A minimal real (non-Mock) stand-in for `self` inside
    TradeExecutor._submit_and_validate_order - only the two attributes that method
    actually reads (order_manager, alpaca_base_url) are real; anything else accessed
    would raise AttributeError exactly like a real bug would, unlike a MagicMock."""

    class _FakeExecutor:
        pass

    fake = _FakeExecutor()
    fake.order_manager = order_manager
    fake.alpaca_base_url = "https://paper-api.alpaca.markets"
    return fake


def test_unfilled_but_accepted_auto_order_is_not_reported_as_failure():
    order_manager = OrderManager(
        alpaca_key="test-key", alpaca_secret="test-secret", alpaca_base_url="https://paper-api.alpaca.markets"
    )
    fake_executor = _make_bound_submit_and_validate_order(order_manager)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = _unfilled_alpaca_response()

    with patch("algo.trading.order_manager.requests.post", return_value=mock_response):
        result = TradeExecutor._submit_and_validate_order(
            fake_executor,
            symbol="TEST",
            trade_id="TRD-UNFILLED1",
            shares=Decimal("10"),
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
            target_1_price=Decimal("110.00"),
            execution_mode="auto",
            idempotency_key="idem-test-unfilled",
        )

    order_ok, alpaca_order_id, order_status, order_error, executed_price, _rejection_reason, order_result = result

    # The core assertion: an accepted-but-unfilled order must be reported as a SUCCESSFUL
    # submission (order_ok=True) with executed_price=None (to be resolved later by
    # wait_for_order_fill), NOT as a failure that discards the order entirely.
    assert order_ok is True, f"accepted order was reported as failed: {order_error}"
    assert alpaca_order_id == "alpaca-order-789"
    assert order_status == "new"
    assert executed_price is None
    assert order_result is not None
    assert order_result["legs"] is not None


def test_filled_auto_order_still_returns_executed_price():
    """Companion case: when Alpaca's immediate response already shows a fill (can happen
    for a marketable limit order), executed_price must still be populated as before."""
    order_manager = OrderManager(
        alpaca_key="test-key", alpaca_secret="test-secret", alpaca_base_url="https://paper-api.alpaca.markets"
    )
    fake_executor = _make_bound_submit_and_validate_order(order_manager)

    filled_response = _unfilled_alpaca_response(order_id="alpaca-order-999")
    filled_response["status"] = "filled"
    filled_response["filled_avg_price"] = 100.5

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = filled_response

    with patch("algo.trading.order_manager.requests.post", return_value=mock_response):
        result = TradeExecutor._submit_and_validate_order(
            fake_executor,
            symbol="TEST",
            trade_id="TRD-FILLED1",
            shares=Decimal("10"),
            entry_price=Decimal("100.00"),
            stop_loss_price=Decimal("90.00"),
            target_1_price=Decimal("110.00"),
            execution_mode="auto",
            idempotency_key="idem-test-filled",
        )

    order_ok, _alpaca_order_id, order_status, _order_error, executed_price, _rejection_reason, _order_result = result

    assert order_ok is True
    assert order_status == "filled"
    assert executed_price == Decimal("100.5")
