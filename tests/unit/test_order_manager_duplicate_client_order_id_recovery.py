"""Regression tests for the 2026-07-27 fix: OrderManager.send_bracket_order/send_market_exit
treated ANY non-200/201 Alpaca response as a hard failure, including the specific case where
client_order_id was rejected because an earlier attempt (whose response was lost to a
timeout/crash) already succeeded at the broker - exactly the scenario the crash-recovery
client_order_id reuse (see test_order_manager_exit_idempotency.py,
executor.py:_send_alpaca_exit) is designed to produce on retry.

Fixed by adding OrderManager._lookup_order_by_client_order_id: on a rejected resubmission,
check ground truth (does an order with this client_order_id exist at the broker?) via
GET /v2/orders:by_client_order_id, rather than reporting a false failure for an order that
actually went through. Falls through to the original failure unchanged if the lookup finds
nothing (genuine validation failure) or is itself inconclusive (network error, 404).

See memory: project_client_order_id_duplicate_rejection_not_handled.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


class TestExitDuplicateRecovery:
    def test_422_with_existing_order_returns_original_success(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "real-order-123",
            "status": "filled",
            "filled_avg_price": "101.50",
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_market_exit("AAPL", 5, "auto", client_order_id="exit-42-abc123")

        assert result["success"] is True
        assert result["order_id"] == "real-order-123"
        assert result["filled_price"] == 101.50

    def test_422_with_no_existing_order_still_fails(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="invalid quantity")
        lookup_resp = MagicMock(status_code=404)

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_market_exit("AAPL", 5, "auto", client_order_id="exit-42-abc123")

        assert result["success"] is False

    def test_422_lookup_network_error_still_fails_original_way(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="invalid quantity")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch(
                "algo.trading.order_manager.requests.get",
                side_effect=requests.exceptions.ConnectionError("network down"),
            ),
        ):
            result = manager.send_market_exit("AAPL", 5, "auto", client_order_id="exit-42-abc123")

        assert result["success"] is False

    def test_no_client_order_id_skips_lookup_entirely(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="invalid quantity")

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get") as mock_get,
        ):
            result = manager.send_market_exit("AAPL", 5, "auto", client_order_id=None)

        mock_get.assert_not_called()
        assert result["success"] is False


class TestEntryDuplicateRecovery:
    def test_rejection_with_existing_order_returns_original_success(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="client order id must be unique")
        lookup_resp = MagicMock(status_code=200)
        lookup_resp.json.return_value = {
            "id": "real-order-456",
            "status": "filled",
            "order_class": "bracket",
            "filled_avg_price": "50.25",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "held"},
                {"id": "leg-tp", "type": "limit", "status": "held"},
            ],
        }

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order(
                "MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-xyz"
            )

        assert result["success"] is True
        assert result["order_id"] == "real-order-456"

    def test_rejection_with_no_existing_order_still_fails(self):
        manager = _make_manager()
        reject_resp = MagicMock(status_code=422, text="invalid quantity")
        lookup_resp = MagicMock(status_code=404)

        with (
            patch("algo.trading.order_manager.requests.post", return_value=reject_resp),
            patch("algo.trading.order_manager.requests.get", return_value=lookup_resp),
        ):
            result = manager.send_bracket_order(
                "MSFT", 10, 50.0, stop_loss_price=48.0, client_order_id="idem-key-xyz"
            )

        assert result["success"] is False


class TestLookupHelperConservatism:
    def test_lookup_returns_none_without_credentials(self):
        manager = OrderManager("", "", "https://paper-api.alpaca.markets")
        assert manager._lookup_order_by_client_order_id("some-id") is None

    def test_lookup_returns_none_on_malformed_200_body(self):
        manager = _make_manager()
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"no_id_field": True}
        with patch("algo.trading.order_manager.requests.get", return_value=resp):
            assert manager._lookup_order_by_client_order_id("some-id") is None
