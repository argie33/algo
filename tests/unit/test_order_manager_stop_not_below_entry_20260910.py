"""Regression test: OrderManager.send_bracket_order() must reject a stop_loss_price that
is not below entry_price for a long-side bracket order - pre-live-money audit, 2026-09-10.

Every price field was individually validated for NaN/Infinity/magnitude, but nothing
checked the relationship between stop_loss_price and entry_price. A stop at or above
entry is satisfiable the instant the buy fills, producing an immediate self-liquidating
round-trip loss with no real protective distance.
"""

from unittest.mock import patch

import algo.reporting.notifications as notifications_module
from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def test_stop_equal_to_entry_is_rejected():
    manager = _make_manager()
    with patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("AAPL", 10, 100.0, 100.0, None, None)

    assert result["success"] is False
    assert "stop_loss_price" in result["message"]
    mock_notify.assert_called_once()


def test_stop_above_entry_is_rejected():
    manager = _make_manager()
    with patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("MSFT", 10, 100.0, 105.0, None, None)

    assert result["success"] is False
    assert "stop_loss_price" in result["message"]
    mock_notify.assert_called_once()


def test_stop_below_entry_still_succeeds():
    manager = _make_manager()
    with patch("algo.trading.order_manager.requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "id": "real-order-1",
            "status": "filled",
            "order_class": "bracket",
            "filled_avg_price": "100.00",
            "legs": [
                {"id": "leg-stop", "type": "stop", "status": "held"},
                {"id": "leg-tp", "type": "limit", "status": "held"},
            ],
        }
        result = manager.send_bracket_order("GOOG", 10, 100.0, 90.0, None, "idem-1")

    assert result["success"] is True
