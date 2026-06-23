#!/usr/bin/env python3
"""
Alert Escalation — Notify on critical data/trading issues

Sends emails + webhook alerts when patrol finds critical/error issues.
Configuration via environment variables:
  ALERT_EMAIL_FROM: sender address
  ALERT_EMAIL_TO: comma-separated recipients
  ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER, ALERT_SMTP_PASSWORD
  ALERT_WEBHOOK_URL: optional Slack/Teams/custom webhook
"""

import json
import logging
import os
import re
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import urlparse

import requests

from algo.infrastructure import get_webhook_timeout

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False


def _validate_webhook_url(url: str) -> bool:
    """Validate webhook URL is safe (not SSRF attack).

    Rules:
    - Must be HTTPS only
    - Only allow whitelisted domains (Slack, Teams, Discord, custom)
    - Block private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.1, 169.254.0.0/16)
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        return False

    # Must be HTTPS
    if parsed.scheme != "https":
        logger.warning(f"Webhook URL validation failed: not HTTPS - {url}")
        return False

    hostname = parsed.hostname
    if not hostname:
        logger.warning(f"Webhook URL validation failed: no hostname - {url}")
        return False

    # Block localhost and 127.0.0.1
    if hostname in ("localhost", "127.0.0.1"):
        logger.warning(f"Webhook URL validation failed: localhost - {url}")
        return False

    # Block private/internal IP ranges
    private_ip_patterns = [
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[01])\.",
        r"^192\.168\.",
        r"^169\.254\.",  # AWS metadata service
        r"^127\.",
        r"^::1$",  # IPv6 localhost
        r"^fc00:",  # IPv6 private
        r"^fe80:",  # IPv6 link-local
    ]

    for pattern in private_ip_patterns:
        if re.match(pattern, hostname):
            logger.warning(f"Webhook URL validation failed: private IP - {url}")
            return False

    # Whitelist allowed webhook providers
    allowed_domains = [
        "hooks.slack.com",
        "outlook.webhook.office.com",
        "discordapp.com",
        "cdn.discordapp.com",
        "discord.com",
    ]

    # Allow custom domains if they're in whitelist env var
    custom_domains = os.getenv("WEBHOOK_ALLOWED_DOMAINS", "").split(",")
    custom_domains = [d.strip() for d in custom_domains if d.strip()]

    allowed_domains.extend(custom_domains)

    # Check if hostname or any parent domain is whitelisted
    for allowed in allowed_domains:
        if hostname == allowed or hostname.endswith("." + allowed):
            logger.info(f"Webhook URL validation passed for {allowed}")
            return True

    logger.warning(f"Webhook URL validation failed: domain not whitelisted - {hostname}")
    return False


class AlertManager:
    """Send alerts via email, SNS, and webhook. Fails hard if no channels configured."""

    def __init__(self) -> None:
        self.email_from = os.getenv("ALERT_SMTP_FROM") or os.getenv("ALERT_EMAIL_FROM", "noreply@algo.local")
        self.email_to = [e.strip() for e in os.getenv("ALERT_EMAIL_TO", "").split(",") if e.strip()]
        self.smtp_host = os.getenv("ALERT_SMTP_HOST")
        self.smtp_port = int(os.getenv("ALERT_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("ALERT_SMTP_USER", "")
        self.smtp_password = os.getenv("ALERT_SMTP_PASSWORD", "")

        # Warn and disable email if ALERT_EMAIL_TO is set but SMTP credentials are incomplete.
        # This lets SNS or webhook serve as the primary channel when SMTP is not configured.
        if self.email_to and not (self.smtp_host and self.smtp_user and self.smtp_password):
            logger.warning(
                "Email alerts configured (ALERT_EMAIL_TO set) but SMTP credentials incomplete — "
                "email alerts disabled. Set ALERT_SMTP_HOST, ALERT_SMTP_USER, ALERT_SMTP_PASSWORD "
                "to enable email, or configure ALERTS_SNS_TOPIC / ALERT_WEBHOOK_URL instead."
            )
            self.email_to = []

        # SNS alert channel — used in Lambda where SMTP is unavailable
        self.sns_topic = os.getenv("ALERTS_SNS_TOPIC", "")
        self._sns_client = None

        # SECURITY FIX: Validate webhook URL before using (prevent SSRF)
        webhook_url_raw = os.getenv("ALERT_WEBHOOK_URL", "")
        if webhook_url_raw and not _validate_webhook_url(webhook_url_raw):
            raise RuntimeError(
                f"[SECURITY] Invalid webhook URL in ALERT_WEBHOOK_URL: {webhook_url_raw}. "
                "Must be HTTPS with whitelisted domain (Slack, Teams, Discord)."
            )
        self.webhook_url = webhook_url_raw

        # SMS via Twilio — fail fast if configured but unavailable
        self.phone_numbers = [p.strip() for p in os.getenv("ALERT_PHONE_NUMBERS", "").split(",") if p.strip()]
        self.twilio_client = None
        # Check if SMS is configured but twilio library is not available
        if os.getenv("TWILIO_ACCOUNT_SID") and not TWILIO_AVAILABLE:
            raise RuntimeError(
                "[SMS CONFIG ERROR] Twilio SMS configured (TWILIO_ACCOUNT_SID set) but twilio library not available. "
                "Install twilio with: pip install twilio. Or remove TWILIO_ACCOUNT_SID to disable SMS."
            )
        if os.getenv("TWILIO_ACCOUNT_SID"):
            if not os.getenv("TWILIO_AUTH_TOKEN") or not os.getenv("TWILIO_PHONE_NUMBER"):
                raise RuntimeError(
                    "Twilio SMS configured (TWILIO_ACCOUNT_SID set) but credentials incomplete. "
                    "Set TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER or remove TWILIO_ACCOUNT_SID."
                )
            try:
                self.twilio_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
                self.twilio_from = os.getenv("TWILIO_PHONE_NUMBER", "")
            except (ImportError, ValueError, AttributeError) as e:
                raise RuntimeError(f"Twilio client initialization failed: {e}") from e

        # Fail fast if no alert channels configured
        if not (self.email_to or self.sns_topic or self.webhook_url or self.twilio_client):
            raise RuntimeError(
                "[ALERT CONFIG] No alert channels configured. "
                "Set at least one of: ALERT_EMAIL_TO + ALERT_SMTP_* (email), "
                "ALERTS_SNS_TOPIC (AWS SNS), ALERT_WEBHOOK_URL (Slack/Teams/Discord), "
                "or TWILIO_* (SMS). Cannot proceed without alert capability."
            )

    def _get_sns_client(self) -> Any:
        if self._sns_client is None:
            import boto3

            self._sns_client = boto3.client("sns", region_name=os.getenv("AWS_REGION", "us-east-1"))
        return self._sns_client

    def _publish_sns(self, subject: str, message: str) -> None:
        try:
            self._get_sns_client().publish(
                TopicArn=self.sns_topic,
                Subject=subject[:100],
                Message=message,
            )
            logger.info(f"SNS alert published: {subject}")
        except Exception as e:
            logger.error(f"SNS publish failed: {e}")
            raise

    def send_patrol_alert(self, patrol_run_id: str, counts: dict[str, int], flagged_findings: list[dict[str, str]]) -> None:
        """Send CRITICAL alert when patrol finds issues. Fails hard on send failure.

        Args:
            patrol_run_id: ID of patrol run
            counts: dict with keys 'critical', 'error', 'warn', 'info'
            flagged_findings: list of finding dicts with keys check, severity, target, message

        Raises:
            RuntimeError: If alert sending fails for any configured channel
        """
        critical = counts.get("critical", 0)
        error = counts.get("error", 0)
        warn = counts.get("warn", 0)

        # Only alert on CRITICAL or ERROR (not WARN)
        if critical == 0 and error == 0:
            return

        severity = "CRITICAL" if critical > 0 else "ERROR"
        subject = f"[ALGO ALERT] {severity}: Data Patrol {patrol_run_id}"

        # Build email body
        body_lines = [
            f"Data Patrol Alert — {datetime.now(timezone.utc).isoformat()}",
            f"Run: {patrol_run_id}",
            "",
            "Counts:",
            f"  CRITICAL: {critical}",
            f"  ERROR:    {error}",
            f"  WARN:     {warn}",
            "",
        ]

        if flagged_findings:
            body_lines.append("Findings:")
            for finding in flagged_findings:
                if finding["severity"] in ["critical", "error"]:
                    body_lines.append(
                        f"  [{finding['severity'].upper()}] {finding['check']}: {finding['target']} - {finding['message']}"
                    )
            body_lines.append("")

        body_lines.append("ACTION REQUIRED: Review patrol results and halt trading if necessary.")
        body_text = "\n".join(body_lines)

        # SMS message (short version)
        sms_text = f"[ALGO {severity}] Data Patrol: {critical} critical, {error} error. Check email for details."

        # Data patrol alerts are CRITICAL — they must reach ops or trading should halt.
        # Fail hard if any send fails (don't silently continue).
        send_errors = []

        if self.email_to:
            try:
                self._send_email(subject, body_text)
            except Exception as e:
                send_errors.append(f"Email: {e}")

        if self.sns_topic:
            try:
                self._publish_sns(subject, body_text)
            except Exception as e:
                send_errors.append(f"SNS: {e}")

        if self.phone_numbers and self.twilio_client:
            try:
                self._send_sms(sms_text)
            except Exception as e:
                send_errors.append(f"SMS: {e}")

        if self.webhook_url:
            try:
                self._send_webhook(subject, critical, error, warn, flagged_findings)
            except Exception as e:
                send_errors.append(f"Webhook: {e}")

        if send_errors:
            raise RuntimeError(
                f"[CRITICAL] Data patrol alert send failed for run {patrol_run_id}: {'; '.join(send_errors)}. "
                "Ops team may not have received notification of critical data issues."
            )

    def send_position_alert(self, symbol: str, alert_type: str, message: str, details: dict[str, object] | None = None) -> None:
        """Send alert for position-related issues. Non-blocking (logs errors only).

        Args:
            symbol: stock symbol
            alert_type: 'STUCK_ORDER', 'DIVERGENCE', 'RISK_BREACH', etc.
            message: human-readable message
            details: optional dict with extra context
        """
        subject = f"[ALGO ALERT] {alert_type}: {symbol}"
        body_lines = [
            f"Position Alert — {datetime.now(timezone.utc).isoformat()}",
            f"Type: {alert_type}",
            f"Symbol: {symbol}",
            "",
            f"Message: {message}",
        ]
        if details:
            body_lines.append("")
            body_lines.append("Details:")
            body_lines.append(json.dumps(details, indent=2))

        body_text = "\n".join(body_lines)

        if self.email_to:
            try:
                self._send_email(subject, body_text)
            except (smtplib.SMTPException, RuntimeError, OSError, ConnectionError) as e:
                logger.error(f"Position alert email failed (non-blocking): {e}")

        if self.sns_topic:
            try:
                self._publish_sns(subject, body_text)
            except Exception as e:
                logger.error(f"Position alert SNS failed (non-blocking): {e}")

        if self.webhook_url:
            try:
                self._send_webhook_simple(subject, message, alert_type)
            except (requests.RequestException, RuntimeError, ConnectionError) as e:
                logger.error(f"Position alert webhook failed (non-blocking): {e}")

    def send_loader_alert(self, findings: list[tuple[str, str, str]]) -> None:
        """Send alert when loader fails or data is stale. Non-blocking.

        Args:
            findings: list of (severity, check, message) tuples from LoaderMonitor
        """
        critical = [f for f in findings if f[0] == "CRITICAL"]
        errors = [f for f in findings if f[0] == "ERROR"]

        if not critical and not errors:
            return

        severity = "CRITICAL" if critical else "ERROR"
        subject = f"[ALGO ALERT] {severity}: Data Loader Failure"

        body_lines = [
            f"Loader Health Alert — {datetime.now(timezone.utc).isoformat()}",
            "",
            f"Severity: {severity}",
            "",
        ]

        if critical:
            body_lines.append("CRITICAL FINDINGS:")
            for _, check, msg in critical:
                body_lines.append(f"  • [{check}] {msg}")
            body_lines.append("")

        if errors:
            body_lines.append("ERROR FINDINGS:")
            for _, check, msg in errors:
                body_lines.append(f"  • [{check}] {msg}")
            body_lines.append("")

        body_lines.extend(
            [
                "ACTION REQUIRED:",
                "1. Check loader status: python3 algo_loader_monitor.py --check-freshness",
                "2. Trigger loaders manually: python3 loadpricedaily.py",
                "3. Check logs: tail -f /tmp/algo_loaders.log",
                "",
                f"Report time: {datetime.now(timezone.utc).isoformat()}",
            ]
        )

        body_text = "\n".join(body_lines)

        if self.email_to:
            try:
                self._send_email(subject, body_text)
            except Exception as e:
                logger.error(f"Loader alert email failed (non-blocking): {e}")

        if self.sns_topic:
            try:
                self._publish_sns(subject, body_text)
            except Exception as e:
                logger.error(f"Loader alert SNS failed (non-blocking): {e}")

        if self.webhook_url:
            try:
                self._send_webhook_simple(subject, f"{severity}: Data loaders failing", "LOADER_FAILURE")
            except Exception as e:
                logger.error(f"Loader alert webhook failed (non-blocking): {e}")

    def critical(self, message: str) -> None:
        """Send a generic critical alert. Non-blocking.

        Args:
            message: Alert message
        """
        subject = "[ALGO ALERT] CRITICAL"
        body_text = f"Critical Alert — {datetime.now(timezone.utc).isoformat()}\n\n{message}"

        if self.email_to:
            try:
                self._send_email(subject, body_text)
            except (smtplib.SMTPException, RuntimeError, OSError, ConnectionError) as e:
                logger.error(f"Critical alert email failed (non-blocking): {e}")

        if self.sns_topic:
            try:
                self._publish_sns(subject, body_text)
            except Exception as e:
                logger.error(f"Critical alert SNS failed (non-blocking): {e}")

        if self.webhook_url:
            try:
                self._send_webhook_simple(subject, message, "CRITICAL")
            except (requests.RequestException, RuntimeError, ConnectionError) as e:
                logger.error(f"Critical alert webhook failed (non-blocking): {e}")

        if self.phone_numbers and self.twilio_client:
            try:
                self._send_sms(f"[ALGO CRITICAL] {message[:160]}")
            except (RuntimeError, ValueError, ConnectionError) as e:
                logger.error(f"Critical alert SMS failed (non-blocking): {e}")

    def _send_email(self, subject: str, body: str) -> None:
        """Send email via SMTP."""
        if (
            not self.email_to
            or not self.smtp_host
            or not self.smtp_user
            or not self.smtp_password
            or not self.email_from
        ):
            # Skip email if credentials not configured
            return

        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_from
            msg["To"] = ", ".join(self.email_to)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Email sent: {subject}")
        except (smtplib.SMTPException, RuntimeError, OSError, ConnectionError) as e:
            logger.error(f"Email failed: {e}")
            raise

    def _send_webhook(self, subject: str, critical: int, error: int, warn: int, findings: list[dict[str, str]]) -> None:
        """Send Slack-compatible webhook."""
        if not self.webhook_url or not _validate_webhook_url(self.webhook_url):
            logger.warning(
                "Webhook URL invalid or not set — skipping webhook. "
                "Configure ALERT_WEBHOOK_URL environment variable to enable Slack alerts."
            )
            return

        try:
            color = "danger" if critical > 0 else "warning"
            text = f"{critical} CRITICAL, {error} ERROR, {warn} WARN"

            finding_text = "\n".join(
                [
                    f"• {f['severity'].upper()}: {f['check']} ({f['target']})"
                    for f in findings
                    if f["severity"] in ["critical", "error"]
                ][:5]
            )

            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": subject,
                        "text": text,
                        "fields": [
                            {
                                "title": "Findings",
                                "value": finding_text or "None",
                                "short": False,
                            }
                        ],
                        "ts": int(datetime.now(timezone.utc).timestamp()),
                    }
                ]
            }
            requests.post(self.webhook_url, json=payload, timeout=get_webhook_timeout())
            logger.info(f"Webhook sent: {subject}")
        except (requests.RequestException, RuntimeError, ConnectionError) as e:
            logger.error(f"Webhook delivery failed: {e}")
            raise

    def _send_webhook_simple(self, title: str, message: str, alert_type: str) -> None:
        """Send simple Slack webhook for position alerts."""
        if not self.webhook_url or not _validate_webhook_url(self.webhook_url):
            logger.warning(
                "Webhook URL invalid or not set — skipping webhook. "
                "Configure ALERT_WEBHOOK_URL environment variable to enable Slack alerts."
            )
            return

        try:
            payload = {
                "attachments": [
                    {
                        "color": "danger",
                        "title": title,
                        "text": message,
                        "fields": [{"title": "Alert Type", "value": alert_type, "short": True}],
                        "ts": int(datetime.now(timezone.utc).timestamp()),
                    }
                ]
            }
            requests.post(self.webhook_url, json=payload, timeout=get_webhook_timeout())
            logger.info(f"Webhook sent: {title}")
        except (requests.RequestException, RuntimeError, ConnectionError) as e:
            logger.error(f"Webhook delivery failed: {e}")
            raise

    def _send_sms(self, message: str) -> None:
        """Send SMS via Twilio to all configured numbers."""
        if not self.twilio_client or not self.twilio_from:
            return

        for phone in self.phone_numbers:
            try:
                self.twilio_client.messages.create(body=message, from_=self.twilio_from, to=phone)
                logger.info(f"SMS sent to {phone}")
            except (RuntimeError, ValueError, ConnectionError) as e:
                logger.error(f"SMS to {phone} failed: {e}")
                raise


class NullAlertManager(AlertManager):
    """Drop-in AlertManager replacement that logs instead of sending alerts.

    Used in dry-run mode when no alert channels are configured.
    All public methods from AlertManager are implemented as log-only no-ops.
    """

    def __init__(self) -> None:
        """Initialize without checking for alert channels (dry-run friendly)."""
        pass

    def send_patrol_alert(self, patrol_run_id: str, counts: dict[str, int], flagged_findings: list[dict[str, str]]) -> None:
        logger.warning(f"[NULL_ALERTS] Patrol alert suppressed (no channels): run_id={patrol_run_id}")

    def send_position_alert(self, symbol: str, alert_type: str, message: str, details: dict[str, object] | None = None) -> None:
        logger.warning(f"[NULL_ALERTS] Position alert suppressed: {symbol} {alert_type} — {message}")

    def send_loader_alert(self, findings: list[tuple[str, str, str]]) -> None:
        logger.warning(f"[NULL_ALERTS] Loader alert suppressed: {len(findings)} findings")

    def critical(self, message: str) -> None:
        logger.warning(f"[NULL_ALERTS] Critical alert suppressed: {message}")


if __name__ == "__main__":
    # Test alerts
    am = AlertManager()
    am.send_patrol_alert(
        "PATROL-20260505-120000",
        {"critical": 1, "error": 2, "warn": 3, "info": 10},
        [
            {
                "check": "staleness",
                "severity": "critical",
                "target": "price_daily",
                "message": "Data stale: 9d > 7d threshold",
            },
            {
                "check": "ohlc_sanity",
                "severity": "error",
                "target": "price_daily",
                "message": "5 rows with High < Low (data corruption)",
            },
        ],
    )
