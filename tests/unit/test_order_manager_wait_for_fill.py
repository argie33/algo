#!/usr/bin/env python3
"""Regression test: wait_for_order_fill() crashed with an uncaught KeyError instead of
returning its documented (success, filled_price, error_message) tuple when Alpaca reported
a terminal status (cancelled/rejected/expired) without a 'cancel_reason' key in the response.

utils/validation/alpaca.py's own AlpacaResponseValidator already falls back through
cancel_reason -> failed_reason -> reason for exactly this reason (Alpaca does not guarantee
'cancel_reason' is present for every terminal status), but order_manager.py's
wait_for_order_fill() used a bare data["cancel_reason"] subscript with no such fallback and
no exception handling around it - any caller of this function (order entry flow) would see
an unhandled crash instead of a graceful rejection result.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _mock_response(status, extra=None):
    resp = MagicMock()
    resp.status_code = 200
    data = {"status": status}
    if extra:
        data.update(extra)
    resp.json.return_value = data
    return resp


class TestWaitForOrderFillTerminalStatus:
    def test_rejected_without_cancel_reason_does_not_raise(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("rejected"),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is False
        assert filled_price is None
        assert "rejected" in error_msg

    def test_cancelled_with_cancel_reason_uses_it(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("cancelled", {"cancel_reason": "user requested"}),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is False
        assert filled_price is None
        assert "user requested" in error_msg

    def test_expired_falls_back_to_reason_field(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("expired", {"reason": "market closed"}),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is False
        assert filled_price is None
        assert "market closed" in error_msg


class TestWaitForOrderFillPartialFillAndPriceFormat:
    """Regression tests for the 2026-08-11 fix: found via adversarial fuzzing of order state
    transitions.

    Bug 1: "partially_filled" fell through to the "Unknown order status" branch, returning
    (False, None, ...) - the same "order did not fill, do NOT write to DB" contract as a real
    rejection. But a partial fill means real shares were already bought at the broker - the
    caller would cancel the remaining bracket and never record the shares that DID fill, the
    same "invisible live position" bug class as 9ab154003/263137d81 reached via a different
    order state.

    Bug 2: filled_avg_price was used directly in an f-string ":.2f" format before being cast
    to float. Alpaca's real API returns this field as a JSON string (confirmed by
    utils/validation/alpaca.py's AlpacaResponseValidator, which already explicitly
    float()-converts it) - so every real fill confirmation raised an unhandled
    `ValueError: Unknown format code 'f' for object of type 'str'`, not caught by this loop's
    own except clause (only catches requests exceptions).
    """

    def test_partially_filled_is_treated_as_success_not_unknown_status(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("partially_filled", {"filled_avg_price": "100.50"}),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is True, "a partial fill is a real fill and must not be reported as failure"
        assert filled_price == 100.50
        assert error_msg == ""

    def test_filled_with_string_price_does_not_raise(self):
        """Alpaca's real API returns filled_avg_price as a string - this must not crash."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("filled", {"filled_avg_price": "99.75"}),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is True
        assert filled_price == 99.75
        assert isinstance(filled_price, float)

    def test_partially_filled_with_string_price_does_not_raise(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("partially_filled", {"filled_avg_price": "50.25"}),
        ):
            success, filled_price, error_msg = manager.wait_for_order_fill("TEST", "order-123")

        assert success is True
        assert filled_price == 50.25
