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
