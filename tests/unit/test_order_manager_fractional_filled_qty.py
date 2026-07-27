"""Regression test: get_order_filled_quantity() crashed with an uncaught ValueError for
any fractionally-filled order.

Alpaca's REST API returns filled_qty as a STRING to preserve decimal precision (e.g.
"4.87" for a fractional-share fill) - this system actively trades fractional shares
(confirmed real open positions with quantities like 0.50, 2.81, 5.87 shares). The
function's own declared return type is `float | None`, but it called `int(filled_qty)`,
which raises `ValueError: invalid literal for int() with base 10: '4.87'` for any
non-whole-share fill. This ValueError isn't in the retry loop's except clause (which only
catches requests.RequestException/Timeout), so it propagated uncaught out of the function
- crashing entry/exit fill verification (executor_entry_handler.py,
executor_exit_handler.py) for any fractionally-filled live/paper order.
"""

from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _mock_response(filled_qty):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"filled_qty": filled_qty}
    return resp


class TestGetOrderFilledQuantityFractionalShares:
    def test_fractional_fill_does_not_raise(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("4.87"),
        ):
            result = manager.get_order_filled_quantity("order-123")

        assert result == 4.87

    def test_whole_share_fill_still_works(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")
        with patch(
            "algo.trading.order_manager.requests.get",
            return_value=_mock_response("10"),
        ):
            result = manager.get_order_filled_quantity("order-123")

        assert result == 10.0
