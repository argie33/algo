"""Regression test: OrderManager.send_bracket_order()'s defense-in-depth execution_mode
guard (2026-09-10 order-execution re-audit, hardened same day to fail closed).
send_bracket_order() refuses to submit unless execution_mode == "auto" or the resolved
base_url looks like the paper endpoint - including when the constructor was never given an
execution_mode at all, so a future caller that forgets to pass it fails closed instead of
silently getting no gate.
"""

from unittest.mock import patch

import algo.reporting.notifications as notifications_module
from algo.trading.order_manager import OrderManager


def test_no_execution_mode_supplied_against_live_url_is_aborted():
    """A caller that omits execution_mode entirely must still be blocked against a
    non-paper base_url - omission is not a way to bypass the gate."""
    manager = OrderManager("key", "secret", "https://live-api.alpaca.markets")
    assert manager.execution_mode is None
    with patch("requests.post") as mock_post, patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("AAPL", 10, 100.0, 90.0, None, None)
    assert result["success"] is False
    mock_post.assert_not_called()
    mock_notify.assert_called_once()


def test_no_execution_mode_supplied_against_paper_url_is_allowed():
    """A caller that omits execution_mode is still fine against the paper endpoint."""
    manager = OrderManager("key", "secret", "https://paper-api.alpaca.markets")
    assert manager.execution_mode is None
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "boom"
        manager.send_bracket_order("AAPL", 10, 100.0, 90.0, None, None)
    mock_post.assert_called_once()


def test_non_auto_mode_against_live_url_is_aborted():
    manager = OrderManager("key", "secret", "https://live-api.alpaca.markets", execution_mode="paper")
    with patch("requests.post") as mock_post, patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("AAPL", 10, 100.0, 90.0, None, None)

    assert result["success"] is False
    assert "execution_mode" in result["message"]
    mock_post.assert_not_called()
    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert args[0] == "critical"
    assert kwargs.get("symbol") == "AAPL"


def test_non_auto_mode_against_paper_url_is_allowed():
    """A dry/review run against the paper endpoint is legitimate and must not be blocked."""
    manager = OrderManager("key", "secret", "https://paper-api.alpaca.markets", execution_mode="dry")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "boom"
        manager.send_bracket_order("AAPL", 10, 100.0, 90.0, None, None)
    mock_post.assert_called_once()


def test_auto_mode_against_live_url_is_allowed():
    manager = OrderManager("key", "secret", "https://live-api.alpaca.markets", execution_mode="auto")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 500
        mock_post.return_value.text = "boom"
        manager.send_bracket_order("AAPL", 10, 100.0, 90.0, None, None)
    mock_post.assert_called_once()
