#!/usr/bin/env python3
"""Notification Dispatcher - Handle trade event notifications and TCA recording."""

import logging
import time
from decimal import Decimal
from typing import Any

from algo.reporting import TradeNotificationService, notify
from algo.trading.exceptions import DatabaseError, NotificationError

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches trade event notifications and records TCA metrics."""

    def __init__(self, config: Any, tca_engine: Any = None) -> None:
        """Initialize notification dispatcher.

        Args:
            config: Algo configuration
            tca_engine: Optional TCAEngine instance for recording execution quality
        """
        self.config = config
        self.notification_service = TradeNotificationService(config)
        self.tca_engine = tca_engine

    def record_entry_and_notify(
        self,
        trade_id: str,
        symbol: str,
        entry_price: Decimal,
        executed_price: Decimal,
        shares: Decimal,
        actual_shares: Decimal,
        stop_loss_price: Decimal,
        target_1_price: Decimal | None,
        swing_score: float | None,
        base_type: str | None,
        execution_mode: str,
        order_send_time: float | None = None,
    ) -> dict[str, Any]:
        """Record entry execution quality (TCA) and send notifications.

        Returns dict with any alerts that were generated.
        """
        tca_result = {}

        if execution_mode == "auto" and self.tca_engine and order_send_time:
            if not order_send_time:
                raise RuntimeError(
                    f"[TCA CRITICAL] {symbol}: order_send_time not set in AUTO mode. "
                    "Cannot record TCA without accurate send timestamp."
                )
            execution_latency_ms = int((time.time() - order_send_time) * 1000)
            if execution_latency_ms < 0:
                raise ValueError(
                    f"[TCA CRITICAL] {symbol}: negative latency {execution_latency_ms}ms. "
                    "Clock skew or time tracking error."
                )

            try:
                tca_result = self.tca_engine.record_fill(
                    trade_id=(int(trade_id) if isinstance(trade_id, str) and trade_id.isdigit() else 0),
                    symbol=symbol,
                    signal_price=float(entry_price),
                    fill_price=float(executed_price),
                    shares_requested=int(shares),
                    shares_filled=int(actual_shares),
                    side="BUY",
                    execution_latency_ms=execution_latency_ms,
                )
                if "alert" in tca_result:
                    try:
                        alert_data = tca_result["alert"]
                        notify(
                            alert_data["severity"].lower(),
                            title=f"TCA Alert: {alert_data['severity']}",
                            message=alert_data["message"],
                        )
                    except NotificationError as alert_e:
                        logger.warning(f"Failed to send TCA alert (non-blocking): {alert_e}")
            except DatabaseError as tca_e:
                logger.warning(f"TCA recording failed (database error): {tca_e} (non-blocking)")

        try:
            self.notification_service._send_notification(
                subject=f"ENTRY: {symbol}",
                message=f"{actual_shares:.2f} sh {symbol} @ ${(executed_price or entry_price):.2f} (stop ${stop_loss_price:.2f})",
                kind="trade_entry",
                severity="info",
                symbol=symbol,
                details={
                    "entry_price": executed_price,
                    "shares": float(actual_shares),
                    "stop_loss": stop_loss_price,
                    "target_1": target_1_price,
                    "swing_score": swing_score,
                    "base_type": base_type,
                    "trade_id": trade_id,
                },
            )
        except NotificationError as notif_e:
            logger.error(f"Failed to send entry notification for {symbol}: {notif_e}")
            raise RuntimeError(f"Critical: Entry notification failed for {symbol}") from notif_e

        return tca_result

    def notify_entry_executed(self, symbol: str, entry_price: float, shares: int, stop_loss: float) -> None:
        """Notify of trade entry execution."""
        try:
            message = f"Entry: {symbol} @ ${entry_price:.2f}, {shares}sh, stop ${stop_loss:.2f}"
            notify("info", title="Trade Entry", message=message)
            logger.info(f"[NOTIFY_ENTRY] {symbol}: ${entry_price:.2f} x {shares}sh, stop=${stop_loss:.2f}")
        except Exception as e:
            logger.error(f"Critical: Failed to send entry notification for {symbol}: {e}")
            raise RuntimeError(f"Critical: Entry notification failed for {symbol}") from e

    def notify_exit_executed(self, symbol: str, exit_price: float, shares: int, pnl: float, pnl_pct: float) -> None:
        """Notify of trade exit execution."""
        try:
            message = f"Exit: {symbol} @ ${exit_price:.2f}, {shares}sh, P&L=${pnl:.2f} ({pnl_pct:+.1f}%)"
            notify("info", title="Trade Exit", message=message)
            logger.info(f"[NOTIFY_EXIT] {symbol}: ${exit_price:.2f} x {shares}sh, PnL=${pnl:.2f}")
        except Exception as e:
            logger.error(f"Critical: Failed to send exit notification for {symbol}: {e}")
            raise RuntimeError(f"Critical: Exit notification failed for {symbol}") from e

    def notify_trade_error(self, symbol: str, error: str) -> None:
        """Notify of trade execution error."""
        try:
            notify("error", title="Trade Failed", message=f"{symbol}: {error}")
            logger.error(f"[NOTIFY_ERROR] {symbol}: {error}")
        except Exception as e:
            logger.error(f"Critical: Failed to send error notification for {symbol}: {e}")
            raise RuntimeError(f"Critical: Error notification failed for {symbol}") from e

    def notify_position_alert(self, symbol: str, alert_type: str, message: str) -> None:
        """Notify of position-related alert."""
        try:
            notify(
                "warning",
                title=f"Position Alert: {alert_type}",
                message=f"{symbol}: {message}",
            )
            logger.warning(f"[NOTIFY_ALERT] {symbol} {alert_type}: {message}")
        except Exception as e:
            logger.error(f"Critical: Failed to send position alert notification for {symbol}: {e}")
            raise RuntimeError(f"Critical: Position alert notification failed for {symbol}") from e
