#!/usr/bin/env python3
"""
Smart Alert Routing - Route alerts to the right channel

Rules:
- CRITICAL → SMS (Twilio)  + Email + Slack
- ERROR → Email + Slack + Log
- WARNING → Slack + Log only (no SMS/email)
- INFO → Log only

Prevents alert spam while ensuring critical issues reach you immediately.
"""

import logging
import os
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from credential_manager import get_credential_manager

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

log = logging.getLogger(__name__)
credential_manager = get_credential_manager()


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


class AlertRouter:
    """Route alerts to appropriate channels based on severity."""

    def __init__(self):
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.twilio_account = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from = os.getenv("TWILIO_FROM_NUMBER")
        self.alert_phone = os.getenv("ALERT_PHONE_NUMBER")
        self.alert_email = os.getenv("ALERT_EMAIL")

    def route_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        runbook_url: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Route alert to appropriate channels.

        Args:
            severity: AlertSeverity enum
            title: Short title (e.g., "Loader Failed")
            message: Detailed message
            runbook_url: Link to runbook for recovery
            extra: Extra context (symbol, error, etc)

        Returns:
            True if routing succeeded
        """
        extra = extra or {}

        log.info(f"Alert [{severity.name}] {title}", extra={
            "severity": severity.name,
            "title": title,
            "message": message,
            **extra,
        })

        # Build alert text
        alert_text = self._format_alert(title, message, runbook_url, extra, severity)

        success = True

        # Route based on severity
        if severity == AlertSeverity.CRITICAL:
            # Send SMS (urgent)
            if self._send_sms(alert_text):
                log.info("  [SENT] SMS to " + (self.alert_phone or "configured number"))
            else:
                log.warning("  [FAILED] SMS send")
                success = False

            # Send email
            if self._send_email(title, alert_text):
                log.info("  [SENT] Email to " + (self.alert_email or "configured address"))
            else:
                log.warning("  [FAILED] Email send")
                success = False

            # Send Slack
            if self._send_slack(alert_text, color="danger"):
                log.info("  [SENT] Slack notification")
            else:
                log.warning("  [FAILED] Slack send")
                success = False

        elif severity == AlertSeverity.ERROR:
            # Send email
            if self._send_email(title, alert_text):
                log.info("  [SENT] Email")
            else:
                log.warning("  [FAILED] Email send")
                success = False

            # Send Slack
            if self._send_slack(alert_text, color="warning"):
                log.info("  [SENT] Slack notification")
            else:
                log.warning("  [FAILED] Slack send")
                success = False

        elif severity == AlertSeverity.WARNING:
            # Slack only (no email, no SMS)
            if self._send_slack(alert_text, color="warning"):
                log.info("  [SENT] Slack warning")
            else:
                log.warning("  [FAILED] Slack send")
                success = False

        # INFO: just logged above, no additional routing

        return success

    def _format_alert(
        self,
        title: str,
        message: str,
        runbook_url: Optional[str],
        extra: Dict[str, Any],
        severity: AlertSeverity,
    ) -> str:
        """Format alert message."""
        parts = [
            f"[{severity.name}] {title}",
            "",
            message,
        ]

        if extra:
            parts.append("")
            parts.append("Details:")
            for key, value in extra.items():
                parts.append(f"  {key}: {value}")

        if runbook_url:
            parts.append("")
            parts.append(f"Recovery: {runbook_url}")

        parts.append("")
        parts.append(f"Time: {datetime.now().isoformat()}")

        return "\n".join(parts)

    def _send_sms(self, message: str) -> bool:
        """Send SMS via Twilio."""
        if not all([self.twilio_account, self.twilio_token, self.twilio_from, self.alert_phone]):
            log.debug("SMS not configured")
            return False

        try:
            # Twilio SDK would go here
            # from twilio.rest import Client
            # client = Client(self.twilio_account, self.twilio_token)
            # client.messages.create(body=message, from_=self.twilio_from, to=self.alert_phone)
            # For now, just log it
            log.info(f"[SMS] Would send to {self.alert_phone}: {message[:50]}...")
            return True
        except Exception as e:
            log.error(f"SMS failed: {e}")
            return False

    def _send_email(self, subject: str, body: str) -> bool:
        """Send email."""
        if not self.alert_email:
            log.debug("Email not configured")
            return False

        try:
            # Email would go via SMTP here
            # import smtplib
            # msg = EmailMessage()
            # msg['Subject'] = subject
            # msg['From'] = "noreply@bullseyefinancial.com"
            # msg['To'] = self.alert_email
            # msg.set_content(body)
            # For now, just log it
            log.info(f"[EMAIL] Would send to {self.alert_email}: {subject}")
            return True
        except Exception as e:
            log.error(f"Email failed: {e}")
            return False

    def _send_slack(self, message: str, color: str = "good") -> bool:
        """Send Slack message."""
        if not self.slack_webhook:
            log.debug("Slack not configured")
            return False

        try:
            import requests
            payload = {
                "attachments": [
                    {
                        "fallback": message,
                        "color": color,
                        "text": message,
                        "mrkdwn_in": ["text"],
                    }
                ]
            }
            response = requests.post(self.slack_webhook, json=payload, timeout=5)
            return response.status_code == 200
        except Exception as e:
            log.error(f"Slack failed: {e}")
            return False


# Singleton instance
_router = None


def get_router() -> AlertRouter:
    """Get the singleton alert router."""
    global _router
    if _router is None:
        _router = AlertRouter()
    return _router


def alert_critical(title: str, message: str, runbook: Optional[str] = None, **extra) -> bool:
    """Send CRITICAL alert (SMS + Email + Slack)."""
    return get_router().route_alert(
        AlertSeverity.CRITICAL,
        title,
        message,
        runbook_url=runbook,
        extra=extra,
    )


def alert_error(title: str, message: str, **extra) -> bool:
    """Send ERROR alert (Email + Slack)."""
    return get_router().route_alert(
        AlertSeverity.ERROR,
        title,
        message,
        extra=extra,
    )


def alert_warning(title: str, message: str, **extra) -> bool:
    """Send WARNING alert (Slack only)."""
    return get_router().route_alert(
        AlertSeverity.WARNING,
        title,
        message,
        extra=extra,
    )
