#!/usr/bin/env python3
"""Regression test: send_market_exit() submits a marketable limit order when given a
limit_price, and preserves the original unconditional market-order behavior otherwise.

Context: every algo exit used to submit a naked market order with zero price protection,
even for non-urgent exits (profit targets, time-based, portfolio rotation) that have no
reason to forfeit fill-price control. executor.py now computes a limit_price for non-urgent
exits (see test_executor_exit_limit_price_urgency.py) and passes it here; hard stop-loss
exits still pass limit_price=None (unchanged pure market order - certainty of exit wins).
"""

import math
from unittest.mock import MagicMock, patch

from algo.trading.order_manager import OrderManager


def _mock_response(status_code=200, order_id="exit-order-1", filled_avg_price=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "id": order_id,
        "status": "new",
        "filled_avg_price": filled_avg_price,
    }
    return resp


class TestSendMarketExitMarketableLimit:
    def test_limit_price_none_submits_plain_market_order(self):
        """Default/unchanged behavior: no limit_price -> type=market, no limit_price field."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "market"
        assert "limit_price" not in payload

    def test_valid_limit_price_submits_limit_order(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", limit_price=49.755)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "limit"
        assert payload["limit_price"] == "49.76"  # ROUND_HALF_UP, 2 decimals for >= $1

    def test_sub_dollar_limit_price_uses_four_decimals(self):
        """SEC Rule 612 sub-penny rule - same quantization as bracket orders."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", limit_price=0.12345)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "limit"
        assert payload["limit_price"] == "0.1235"  # 4 decimals, ROUND_HALF_UP

    def test_nan_limit_price_falls_back_to_market_order(self):
        """A corrupted limit_price must never reach the broker - fail open to market, not crash."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", limit_price=math.nan)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "market"
        assert "limit_price" not in payload

    def test_non_positive_limit_price_falls_back_to_market_order(self):
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", limit_price=0.0)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["type"] == "market"

    def test_limit_order_still_carries_client_order_id(self):
        """The marketable-limit path must not lose the idempotency protection."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        with patch("algo.trading.order_manager.requests.post", return_value=_mock_response()) as mock_post:
            manager.send_market_exit("TEST", 10, execution_mode="auto", client_order_id="exit-abc123", limit_price=50.0)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["client_order_id"] == "exit-abc123"
        assert payload["type"] == "limit"

    def test_paper_mode_ignores_limit_price(self):
        """Paper/dry/review modes short-circuit before any order type decision."""
        manager = OrderManager("fake_key", "fake_secret", "https://fake.alpaca.test")

        result = manager.send_market_exit("TEST", 10, execution_mode="paper", limit_price=50.0)

        assert result["success"] is True
