#!/usr/bin/env python3
"""Trade & Risk Notifications - Alert on entries, exits, rejections, and risk events."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import psycopg2

from algo.reporting import AlertManager
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TradeNotificationService:
    """Monitor trade events and send notifications."""

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            raise ValueError(
                "TradeNotificationService requires explicit config dict; "
                "silent empty config defaults would cause undetected notification failures"
            )
        self.config = config
        self.alert_manager = AlertManager()
        self.enabled = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

    def get_recent_events(self, minutes: int = 5) -> list[dict[str, Any]]:
        """Fetch recent audit log events."""
        try:
            with DatabaseContext("read") as cur:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
                cur.execute(
                    """
                    SELECT id, action_type, symbol, action_date, details,
                           actor, status, created_at
                    FROM algo_audit_log
                    WHERE created_at >= %s
                    ORDER BY created_at ASC
                """,
                    (cutoff,),
                )
                return cast(list[dict[Any, Any]], cur.fetchall())
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[NOTIF] Failed to fetch events: {e}")
            return []

    def _format_trade_entry_alert(self, event: dict[str, Any]) -> str | None:
        """Format trade entry notification."""
        try:
            details = json.loads(event["details"]) if isinstance(event["details"], str) else event["details"]
            symbol = event.get("symbol") or details.get("symbol")
            if not symbol:
                raise ValueError(
                    f"CRITICAL: Trade entry event missing symbol. "
                    f"Cannot format notification without knowing which symbol was entered. "
                    f"Audit log corruption: event={event.get('id')}, details={details}"
                )
            entry_price = details.get("entry_price")
            shares = details.get("shares")
            stop_loss = details.get("stop_loss")
            target_1 = details.get("target_1")

            return f"""
[ENTRY] TRADE ENTRY -- {symbol}
Entry Price:  ${entry_price:.2f}
Shares:       {shares:.2f}
Stop Loss:    ${stop_loss:.2f}
Target 1:     ${target_1:.2f}
Time:         {event["created_at"].strftime("%H:%M:%S")}
"""
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _format_trade_exit_alert(self, event: dict[str, Any]) -> str | None:
        """Format trade exit notification."""
        try:
            details = json.loads(event["details"]) if isinstance(event["details"], str) else event["details"]
            symbol = event.get("symbol") or details.get("symbol")
            if not symbol:
                raise ValueError(
                    f"CRITICAL: Trade exit event missing symbol. "
                    f"Cannot format notification without knowing which symbol was exited. "
                    f"Audit log corruption: event={event.get('id')}, details={details}"
                )
            exit_price = details.get("exit_price")
            shares = details.get("shares")
            pnl = details.get("pnl")
            exit_reason = details.get("reason")
            if not exit_reason:
                raise ValueError(
                    f"CRITICAL: Trade exit event missing reason. "
                    f"Cannot format notification without knowing exit reason (stop, target, other). "
                    f"Audit log corruption: symbol={symbol}, event={event.get('id')}"
                )

            return f"""
[EXIT] TRADE EXIT -- {symbol}
Exit Price:   ${exit_price:.2f}
Shares:       {shares:.2f}
P&L:          {pnl}
Reason:       {exit_reason}
Time:         {event["created_at"].strftime("%H:%M:%S")}
"""
        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _should_notify(self, action_type: str, status: str) -> bool:
        """Determine if event warrants notification."""
        notify_on = {
            "trade_entry": ["FILLED", "PARTIALLY_FILLED"],
            "trade_exit": ["FILLED", "PARTIALLY_FILLED"],
            "trade_rejection": ["REJECTED"],
            "circuit_breaker": ["TRIGGERED"],
            "error": ["FAILED", "ERROR"],
        }
        for key, values in notify_on.items():
            if key in action_type.lower() and status.upper() in values:
                return True
        return False

    def process_events(self, minutes: int = 5) -> int:
        """Process recent events and send notifications."""
        if not self.enabled:
            return 0

        events = self.get_recent_events(minutes)
        sent = 0
        for event in events:
            action_type = event.get("action_type", "").lower()
            status = event.get("status", "").upper()

            if not self._should_notify(action_type, status):
                continue

            message = None
            subject_prefix = None

            if "trade_entry" in action_type:
                message = self._format_trade_entry_alert(event)
                subject_prefix = f"ENTRY: {event.get('symbol')}"
            elif "trade_exit" in action_type:
                message = self._format_trade_exit_alert(event)
                subject_prefix = f"EXIT: {event.get('symbol')}"

            if message:
                self._send_notification(subject_prefix or action_type, message)
                sent += 1

        return sent

    def _save_notification(
        self,
        kind: str,
        severity: str,
        title: str,
        message: str,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Save notification to database."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_notifications
                    (kind, severity, title, message, symbol, details, seen, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
                """,
                    (
                        kind,
                        severity,
                        title,
                        message,
                        symbol,
                        json.dumps(details) if details else None,
                    ),
                )
                logger.info(f"[NOTIF] Saved to DB: {title}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[NOTIF] DB save failed: {e}")

    def _send_notification(
        self,
        subject: str,
        message: str,
        kind: str = "trade",
        severity: str = "info",
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Send notification via email, webhook, and database."""
        try:
            # Save to database
            self._save_notification(kind, severity, subject, message, symbol, details)

            # Send email alert
            if self.alert_manager.email_to:
                self.alert_manager._send_email(subject=f"[ALGO] {subject}", body=message)
            logger.info(f"[NOTIF] Sent: {subject}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[NOTIF] Send failed: {e}")


def notify(
    severity: str,
    title: str,
    message: str,
    symbol: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Convenience function to send alerts without managing service lifecycle."""
    try:
        service = TradeNotificationService(config={})
        service._send_notification(
            subject=title,
            message=message,
            kind="alert",
            severity=severity,
            symbol=symbol,
            details=details,
        )
    except Exception as e:
        logger.error(f"notify() failed: {e}")


def notify_signal_staleness(stale_tables: list[str], details: dict[str, Any] | None = None) -> None:
    """Alert when trading signals become stale or unavailable.

    Triggered by Phase 1 data freshness check or data patrol when critical
    signal tables (buy_sell_daily, signal_quality_scores, etc.) are outdated.
    """
    try:
        if not stale_tables:
            return

        tables_str = "; ".join(stale_tables[:3])
        if len(stale_tables) > 3:
            tables_str += f" (and {len(stale_tables) - 3} more)"

        message = f"Trading signals based on stale or unavailable data.\n\nAffected: {tables_str}"

        service = TradeNotificationService(config={})
        service._send_notification(
            subject="SIGNAL STALENESS ALERT",
            message=message,
            kind="signal",
            severity="critical",
            details={
                "stale_tables": stale_tables,
                "alert_type": "signal_staleness",
                **(details or {}),
            },
        )
        logger.critical(f"SIGNAL STALENESS ALERT: {tables_str}")
    except Exception as e:
        logger.error(f"notify_signal_staleness() failed: {e}")
