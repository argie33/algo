#!/usr/bin/env python3
"""Trade & Risk Notifications - Alert on entries, exits, rejections, and risk events."""

import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict, List

from algo.algo_alerts import AlertManager
from utils.database_context import database_transaction

logger = logging.getLogger(__name__)

class TradeNotificationService:
    """Monitor trade events and send notifications."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.alert_manager = AlertManager()
        self.enabled = os.getenv("ENABLE_NOTIFICATIONS", "true").lower() == "true"

    def get_recent_events(self, minutes: int = 5) -> List[Dict]:
        """Fetch recent audit log events."""
        try:
            with database_transaction('read') as cur:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
                cur.execute("""
                    SELECT id, action_type, symbol, action_date, details,
                           actor, status, created_at
                    FROM algo_audit_log
                    WHERE created_at >= %s
                    ORDER BY created_at ASC
                """, (cutoff,))
                return cur.fetchall()
        except Exception as e:
            logger.error(f"[NOTIF] Failed to fetch events: {e}")
            return []

    def _format_trade_entry_alert(self, event: Dict) -> Optional[str]:
        """Format trade entry notification."""
        try:
            details = json.loads(event["details"]) if isinstance(event["details"], str) else event["details"]
            symbol = event.get("symbol") or details.get("symbol", "?")
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
        except Exception as e:
            logger.error(f"[NOTIF] Format failed: {e}")
            return None

    def _format_trade_exit_alert(self, event: Dict) -> Optional[str]:
        """Format trade exit notification."""
        try:
            details = json.loads(event["details"]) if isinstance(event["details"], str) else event["details"]
            symbol = event.get("symbol") or details.get("symbol", "?")
            exit_price = details.get("exit_price")
            shares = details.get("shares")
            pnl = details.get("pnl")
            exit_reason = details.get("reason", "unknown")

            return f"""
[EXIT] TRADE EXIT -- {symbol}
Exit Price:   ${exit_price:.2f}
Shares:       {shares:.2f}
P&L:          {pnl}
Reason:       {exit_reason}
Time:         {event["created_at"].strftime("%H:%M:%S")}
"""
        except Exception as e:
            logger.error(f"[NOTIF] Format failed: {e}")
            return None

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

    def _save_notification(self, kind: str, severity: str, title: str,
                           message: str, symbol: Optional[str] = None, details: Optional[dict] = None):
        """Save notification to database."""
        try:
            with database_transaction('write') as cur:
                cur.execute("""
                    INSERT INTO algo_notifications
                    (kind, severity, title, message, symbol, details, seen, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
                """, (
                    kind,
                    severity,
                    title,
                    message,
                    symbol,
                    json.dumps(details) if details else None
                ))
                logger.info(f"[NOTIF] Saved to DB: {title}")
        except Exception as e:
            logger.error(f"[NOTIF] DB save failed: {e}")

    def _send_notification(self, subject: str, message: str, kind: str = "trade",
                          severity: str = "info", symbol: Optional[str] = None, details: Optional[dict] = None):
        """Send notification via email, webhook, and database."""
        try:
            # Save to database
            self._save_notification(kind, severity, subject, message, symbol, details)

            # Send email alert
            if self.alert_manager.email_to:
                self.alert_manager._send_email(
                    subject=f"[ALGO] {subject}",
                    body=message
                )
            logger.info(f"[NOTIF] Sent: {subject}")
        except Exception as e:
            logger.error(f"[NOTIF] Send failed: {e}")

def notify(severity: str, title: str, message: str, symbol: Optional[str] = None, details: Optional[dict] = None):
    """Convenience function to send alerts without managing service lifecycle."""
    try:
        service = TradeNotificationService()
        service._send_notification(
            subject=title,
            message=message,
            kind="alert",
            severity=severity,
            symbol=symbol,
            details=details
        )
    except Exception as e:
        logger.error(f"notify() failed: {e}")
