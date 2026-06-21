#!/usr/bin/env python3
"""Notification Dispatcher - Handle trade event notifications."""

import logging
from typing import Any

from algo.reporting import TradeNotificationService, notify


logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches trade event notifications to appropriate channels."""

    def __init__(self, config: Any) -> None:
        """Initialize notification dispatcher."""
        self.config = config
        self.notification_service = TradeNotificationService(config)

    def notify_entry_executed(self, symbol: str, entry_price: float, shares: int, stop_loss: float) -> None:
        """Notify of trade entry execution."""
        try:
            message = f"Entry: {symbol} @ ${entry_price:.2f}, {shares}sh, stop ${stop_loss:.2f}"
            notify("info", title="Trade Entry", message=message)
            logger.info(f"[NOTIFY_ENTRY] {symbol}: ${entry_price:.2f} x {shares}sh, stop=${stop_loss:.2f}")
        except Exception as e:
            logger.warning(f"Failed to send entry notification: {e}")

    def notify_exit_executed(self, symbol: str, exit_price: float, shares: int, pnl: float, pnl_pct: float) -> None:
        """Notify of trade exit execution."""
        try:
            message = f"Exit: {symbol} @ ${exit_price:.2f}, {shares}sh, P&L=${pnl:.2f} ({pnl_pct:+.1f}%)"
            notify("info", title="Trade Exit", message=message)
            logger.info(f"[NOTIFY_EXIT] {symbol}: ${exit_price:.2f} x {shares}sh, PnL=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"Failed to send exit notification: {e}")

    def notify_trade_error(self, symbol: str, error: str) -> None:
        """Notify of trade execution error."""
        try:
            notify("error", title="Trade Failed", message=f"{symbol}: {error}")
            logger.error(f"[NOTIFY_ERROR] {symbol}: {error}")
        except Exception as e:
            logger.warning(f"Failed to send error notification: {e}")

    def notify_position_alert(self, symbol: str, alert_type: str, message: str) -> None:
        """Notify of position-related alert."""
        try:
            notify("warning", title=f"Position Alert: {alert_type}", message=f"{symbol}: {message}")
            logger.warning(f"[NOTIFY_ALERT] {symbol} {alert_type}: {message}")
        except Exception as e:
            logger.warning(f"Failed to send alert notification: {e}")
