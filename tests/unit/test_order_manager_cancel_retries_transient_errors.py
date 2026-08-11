"""Regression test: OrderManager.cancel_bracket_orders made exactly one attempt, same gap
class as send_bracket_order (see test_order_manager_entry_retries_transient_errors.py) - a
transient Alpaca 429/503 during cancellation was reported as a permanent failure instead of
retried. Callers only log a warning on cancel failure (this cleans up an order already
decided not to become a tracked position), so a failed cancel leaves a real resting bracket
order at the broker with no matching DB record - the orphaned-position class
AlpacaSyncManager._sync_untracked_positions exists to catch later, but retrying here means it
usually never gets that far.

Fixed by giving cancel_bracket_orders the same up-to-3-attempt retry loop as
send_bracket_order/send_market_exit.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


class TestCancelRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_cancelled(self):
        manager = _make_manager()
        rate_limited = MagicMock(status_code=429, text="rate limited")
        cancelled = MagicMock(status_code=204)

        with (
            patch(
                "algo.trading.order_manager.requests.delete",
                side_effect=[rate_limited, cancelled],
            ),
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.cancel_bracket_orders("order-123")

        assert result["success"] is True
        mock_sleep.assert_called_once()

    def test_503_exhausts_all_retries_then_fails(self):
        manager = _make_manager()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=unavailable) as mock_delete,
            patch("algo.trading.order_manager.time.sleep"),
        ):
            try:
                manager.cancel_bracket_orders("order-123")
                raise AssertionError("Expected RuntimeError on all-retries-exhausted")
            except RuntimeError as e:
                assert "Failed to cancel order" in str(e)
                assert mock_delete.call_count == 3

    def test_404_does_not_retry(self):
        """A non-transient error (e.g. order already gone) would fail identically again."""
        manager = _make_manager()
        not_found = MagicMock(status_code=404, text="order not found")

        with (
            patch("algo.trading.order_manager.requests.delete", return_value=not_found) as mock_delete,
        ):
            try:
                manager.cancel_bracket_orders("order-123")
                raise AssertionError("Expected RuntimeError on non-transient error")
            except RuntimeError as e:
                assert "Failed to cancel order" in str(e)
                assert mock_delete.call_count == 1

    def test_network_exception_retries_then_succeeds(self):
        manager = _make_manager()
        cancelled = MagicMock(status_code=200)

        with (
            patch(
                "algo.trading.order_manager.requests.delete",
                side_effect=[requests.exceptions.ConnectionError("network down"), cancelled],
            ),
            patch("algo.trading.order_manager.time.sleep") as mock_sleep,
        ):
            result = manager.cancel_bracket_orders("order-123")

        assert result["success"] is True
        mock_sleep.assert_called_once_with(1)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
