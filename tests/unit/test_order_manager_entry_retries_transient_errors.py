"""Regression test: OrderManager.send_bracket_order (entry orders) used to make exactly one
attempt, unlike send_market_exit's 3-attempt retry loop for the same broker endpoint - a
transient Alpaca 429 (rate limited) or 503 (unavailable) during entry submission was treated
as a permanent rejection, silently losing a real trading opportunity a retry would likely have
recovered. Found 2026-07-28 while auditing order_manager.py for the entry/exit asymmetry.

Fixed by giving send_bracket_order the same up-to-3-attempt retry loop already used by
send_market_exit, retrying only on 429/503 (transient) and on request exceptions - NOT on 422
(unprocessable), which would fail identically again.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def _filled_response():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {
        "id": "real-order-789",
        "status": "filled",
        "order_class": "bracket",
        "filled_avg_price": "50.25",
        "legs": [
            {"id": "leg-stop", "type": "stop", "status": "held"},
            {"id": "leg-tp", "type": "limit", "status": "held"},
        ],
    }
    return resp


class TestEntryRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_filled(self):
        manager = _make_manager()
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch(
                "algo.trading.order_manager.requests.post",
                side_effect=[rate_limited, _filled_response()],
            ),
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert result["success"] is True
        assert result["order_id"] == "real-order-789"
        mock_sleep.assert_called_once()

    def test_503_exhausts_all_retries_then_fails(self):
        manager = _make_manager()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=unavailable),
            patch("algo.trading.order_manager.time.sleep"),
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert result["success"] is False
        assert "503" in result["message"]

    def test_post_call_count_matches_max_attempts_on_persistent_429(self):
        manager = _make_manager()
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=rate_limited) as mock_post,
            patch("algo.trading.order_manager.time.sleep"),
        ):
            manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert mock_post.call_count == 3

    def test_422_does_not_retry(self):
        """A validation error (unprocessable) would fail identically again - must not retry."""
        manager = _make_manager()
        unprocessable = MagicMock(status_code=422, text="invalid quantity")
        lookup_resp = MagicMock(status_code=404)

        with (
            patch("algo.trading.order_manager.requests.post", return_value=unprocessable) as mock_post,
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert result["success"] is False
        assert mock_post.call_count == 1

    def test_network_exception_retries_then_succeeds(self):
        manager = _make_manager()

        with (
            patch(
                "algo.trading.order_manager.requests.post",
                side_effect=[requests.exceptions.ConnectionError("network down"), _filled_response()],
            ),
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert result["success"] is True
        mock_sleep.assert_called_once_with(1)

    def test_first_attempt_success_does_not_sleep_or_retry(self):
        manager = _make_manager()

        with (
            patch("algo.trading.order_manager.requests.post", return_value=_filled_response()) as mock_post,
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.send_bracket_order("MSFT", 10, 50.0, stop_loss_price=48.0)

        assert result["success"] is True
        assert mock_post.call_count == 1
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
