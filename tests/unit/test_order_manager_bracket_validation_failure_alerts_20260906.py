"""Regression test: OrderManager.send_bracket_order()'s corrupted-data validation failures
(invalid entry_price/shares/stop_loss_price/take_profit_price) used to only call
logger.critical() - real-money-readiness audit, 2026-09-06: this is the actual real-order
broker-submission path, and a missing/invalid stop_loss_price specifically means a naked
(unprotected) position was about to be created - exactly the class of event this codebase
already alerts on everywhere else. Each validation-failure branch now also calls notify()
via _notify_bracket_validation_failure, best-effort (must never block the rejection itself).
"""

from unittest.mock import patch

import algo.reporting.notifications as notifications_module
from algo.trading.order_manager import OrderManager


def _make_manager():
    return OrderManager("key", "secret", "https://paper-api.alpaca.markets")


def test_invalid_entry_price_sends_an_alert():
    manager = _make_manager()
    with patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("AAPL", 10, float("nan"), 90.0, None, None)

    assert result["success"] is False
    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert args[0] == "critical"
    assert kwargs.get("symbol") == "AAPL"


def test_invalid_stop_loss_price_sends_an_alert():
    manager = _make_manager()
    with patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("MSFT", 10, 100.0, None, None, None)

    assert result["success"] is False
    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert "stop_loss_price" in args[2]
    assert kwargs.get("symbol") == "MSFT"


def test_invalid_take_profit_price_sends_an_alert():
    manager = _make_manager()
    with patch.object(notifications_module, "notify") as mock_notify:
        result = manager.send_bracket_order("GOOG", 10, 100.0, 90.0, float("inf"), None)

    assert result["success"] is False
    mock_notify.assert_called_once()
    args, kwargs = mock_notify.call_args
    assert "take_profit_price" in args[2]


def test_alert_failure_does_not_block_the_rejection():
    manager = _make_manager()
    with patch.object(notifications_module, "notify", side_effect=RuntimeError("smtp down")):
        result = manager.send_bracket_order("AAPL", 10, float("nan"), 90.0, None, None)

    assert result["success"] is False, "a failed alert delivery must not change the rejection outcome"
