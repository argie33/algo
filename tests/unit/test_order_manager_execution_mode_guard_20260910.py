"""Regression test: OrderManager.send_bracket_order()'s new defense-in-depth execution_mode
guard (2026-09-10 order-execution re-audit). Previously send_bracket_order() had no
execution_mode awareness of its own and relied entirely on its one caller
(executor.py's _submit_and_validate_order) checking execution_mode before calling in -
safe only because grep confirmed a single call site. When the constructor is given an
execution_mode, send_bracket_order() now also refuses to submit if that mode is not
"auto" and the resolved base_url doesn't look like the paper endpoint. Callers that don't
pass execution_mode (the default) get no extra gate here, preserving existing behavior.
"""

from unittest.mock import patch

import algo.reporting.notifications as notifications_module
from algo.trading.order_manager import OrderManager


def test_no_execution_mode_supplied_skips_the_guard():
    """Default behavior (execution_mode=None) is unchanged - request actually goes out."""
    manager = OrderManager("key", "secret", "https://live-api.alpaca.markets")
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
