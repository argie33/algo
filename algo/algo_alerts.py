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

import os
import json
import smtplib
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
import re
from urllib.parse import urlparse
from algo.algo_config import get_webhook_timeout

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
    except Exception:
        return False

    # Must be HTTPS
    if parsed.scheme != 'https':
        logger.warning(f"Webhook URL validation failed: not HTTPS - {url}")
        return False

    hostname = parsed.hostname
    if not hostname:
        logger.warning(f"Webhook URL validation failed: no hostname - {url}")
        return False

    # Block localhost and 127.0.0.1
    if hostname in ('localhost', '127.0.0.1'):
        logger.warning(f"Webhook URL validation failed: localhost - {url}")
        return False

    # Block private/internal IP ranges
    private_ip_patterns = [
        r'^10\.',
        r'^172\.(1[6-9]|2[0-9]|3[01])\.',
        r'^192\.168\.',
        r'^169\.254\.',  # AWS metadata service
        r'^127\.',
        r'^::1$',  # IPv6 localhost
        r'^fc00:',  # IPv6 private
        r'^fe80:',  # IPv6 link-local
    ]

    for pattern in private_ip_patterns:
        if re.match(pattern, hostname):
            logger.warning(f"Webhook URL validation failed: private IP - {url}")
            return False

    # Whitelist allowed webhook providers
    allowed_domains = [
        'hooks.slack.com',
        'outlook.webhook.office.com',
        'discordapp.com',
        'cdn.discordapp.com',
        'discord.com',
    ]

    # Allow custom domains if they're in whitelist env var
    custom_domains = os.getenv('WEBHOOK_ALLOWED_DOMAINS', '').split(',')
    custom_domains = [d.strip() for d in custom_domains if d.strip()]

    allowed_domains.extend(custom_domains)

    # Check if hostname or any parent domain is whitelisted
    for allowed in allowed_domains:
        if hostname == allowed or hostname.endswith('.' + allowed):
            logger.info(f"Webhook URL validation passed for {allowed}")
            return True

    logger.warning(f"Webhook URL validation failed: domain not whitelisted - {hostname}")
    return False


class AlertManager:
    """Send alerts via email and webhook."""

    def __init__(self):
        self.email_from = os.getenv('ALERT_SMTP_FROM') or os.getenv('ALERT_EMAIL_FROM', 'noreply@algo.local')
        self.email_to = [e.strip() for e in os.getenv('ALERT_EMAIL_TO', '').split(',') if e.strip()]
        self.smtp_host = os.getenv('ALERT_SMTP_HOST')
        self.smtp_port = int(os.getenv('ALERT_SMTP_PORT', '587'))
        self.smtp_user = os.getenv('ALERT_SMTP_USER', '')
        self.smtp_password = self._load_smtp_password()

        # SECURITY FIX: Validate webhook URL before using (prevent SSRF)
        webhook_url_raw = os.getenv('ALERT_WEBHOOK_URL', '')
        if webhook_url_raw and not _validate_webhook_url(webhook_url_raw):
            logger.error(f"[SECURITY] Invalid webhook URL rejected: {webhook_url_raw}")
            self.webhook_url = ''
        else:
            self.webhook_url = webhook_url_raw

        # SMS via Twilio
        self.phone_numbers = [p.strip() for p in os.getenv('ALERT_PHONE_NUMBERS', '').split(',') if p.strip()]
        self.twilio_client = None
        if TWILIO_AVAILABLE and os.getenv('TWILIO_ACCOUNT_SID'):
            try:
                self.twilio_client = TwilioClient(
                    os.getenv('TWILIO_ACCOUNT_SID'),
                    os.getenv('TWILIO_AUTH_TOKEN')
                )
                self.twilio_from = os.getenv('TWILIO_PHONE_NUMBER', '')
            except Exception as e:
                logger.warning(f"Twilio init failed: {e}")

        # Warn if alerts are not configured for production
        if not (self.email_to or self.webhook_url or self.twilio_client):
            logger.warning(
                "[ALERT CONFIG] No alert channels configured. "
                "Set ALERT_EMAIL_TO, ALERT_SMTP_USER, and ALERT_SMTP_PASSWORD for email alerts, "
                "or ALERT_WEBHOOK_URL for Slack/Teams, "
                "or Twilio credentials for SMS alerts. "
                "Without alerts, trading issues will not be notified."
            )

    def _load_smtp_password(self) -> str:
        """Load SMTP password from environment variable (set by Lambda or via Terraform)."""
        # Lambda passes ALERT_SMTP_PASSWORD as environment variable
        # Terraform variable alert_smtp_password → Lambda ALERT_SMTP_PASSWORD
        return os.getenv('ALERT_SMTP_PASSWORD', '')

    def send_patrol_alert(self, patrol_run_id, counts, flagged_findings):
        """Send alert when patrol finds issues.

        Args:
            patrol_run_id: ID of patrol run
            counts: dict with keys 'critical', 'error', 'warn', 'info'
            flagged_findings: list of finding dicts with keys check, severity, target, message
        """
        critical = counts.get('critical', 0)
        error = counts.get('error', 0)
        warn = counts.get('warn', 0)

        # Only alert on CRITICAL or ERROR (not WARN)
        if critical == 0 and error == 0:
            return

        severity = 'CRITICAL' if critical > 0 else 'ERROR'
        subject = f'[ALGO ALERT] {severity}: Data Patrol {patrol_run_id}'

        # Build email body
        body_lines = [
            f'Data Patrol Alert — {datetime.now(timezone.utc).isoformat()}',
            f'Run: {patrol_run_id}',
            '',
            'Counts:',
            f'  CRITICAL: {critical}',
            f'  ERROR:    {error}',
            f'  WARN:     {warn}',
            '',
        ]

        if flagged_findings:
            body_lines.append('Findings:')
            for finding in flagged_findings:
                if finding['severity'] in ['critical', 'error']:
                    body_lines.append(
                        f"  [{finding['severity'].upper()}] {finding['check']}: {finding['target']} - {finding['message']}"
                    )
            body_lines.append('')

        body_lines.append('ACTION REQUIRED: Review patrol results and halt trading if necessary.')
        body_text = '\n'.join(body_lines)

        # SMS message (short version)
        sms_text = f"[ALGO {severity}] Data Patrol: {critical} critical, {error} error. Check email for details."

        if self.email_to:
            self._send_email(subject, body_text)

        if self.phone_numbers and self.twilio_client:
            self._send_sms(sms_text)

        if self.webhook_url:
            self._send_webhook(subject, critical, error, warn, flagged_findings)

    def send_position_alert(self, symbol, alert_type, message, details=None):
        """Send alert for position-related issues.

        Args:
            symbol: stock symbol
            alert_type: 'STUCK_ORDER', 'DIVERGENCE', 'RISK_BREACH', etc.
            message: human-readable message
            details: optional dict with extra context
        """
        subject = f'[ALGO ALERT] {alert_type}: {symbol}'
        body_lines = [
            f'Position Alert — {datetime.now(timezone.utc).isoformat()}',
            f'Type: {alert_type}',
            f'Symbol: {symbol}',
            '',
            f'Message: {message}',
        ]
        if details:
            body_lines.append('')
            body_lines.append('Details:')
            body_lines.append(json.dumps(details, indent=2))

        body_text = '\n'.join(body_lines)

        if self.email_to:
            self._send_email(subject, body_text)

        if self.webhook_url:
            self._send_webhook_simple(subject, message, alert_type)

    def send_loader_alert(self, findings):
        """Send alert when loader fails or data is stale.

        Args:
            findings: list of (severity, check, message) tuples from LoaderMonitor
        """
        critical = [f for f in findings if f[0] == 'CRITICAL']
        errors = [f for f in findings if f[0] == 'ERROR']

        if not critical and not errors:
            return

        severity = 'CRITICAL' if critical else 'ERROR'
        subject = f'[ALGO ALERT] {severity}: Data Loader Failure'

        body_lines = [
            f'Loader Health Alert — {datetime.now(timezone.utc).isoformat()}',
            '',
            f'Severity: {severity}',
            '',
        ]

        if critical:
            body_lines.append('CRITICAL FINDINGS:')
            for _, check, msg in critical:
                body_lines.append(f'  • [{check}] {msg}')
            body_lines.append('')

        if errors:
            body_lines.append('ERROR FINDINGS:')
            for _, check, msg in errors:
                body_lines.append(f'  • [{check}] {msg}')
            body_lines.append('')

        body_lines.extend([
            'ACTION REQUIRED:',
            '1. Check loader status: python3 algo_loader_monitor.py --check-freshness',
            '2. Trigger loaders manually: python3 loadpricedaily.py',
            '3. Check logs: tail -f /tmp/algo_loaders.log',
            '',
            f'Report time: {datetime.now(timezone.utc).isoformat()}',
        ])

        body_text = '\n'.join(body_lines)

        if self.email_to:
            self._send_email(subject, body_text)

        if self.webhook_url:
            self._send_webhook_simple(subject, f'{severity}: Data loaders failing', 'LOADER_FAILURE')

    def critical(self, message: str):
        """Send a generic critical alert.

        Args:
            message: Alert message
        """
        subject = '[ALGO ALERT] CRITICAL'
        body_text = f"Critical Alert — {datetime.now(timezone.utc).isoformat()}\n\n{message}"

        if self.email_to:
            self._send_email(subject, body_text)

        if self.webhook_url:
            self._send_webhook_simple(subject, message, 'CRITICAL')

        if self.phone_numbers and self.twilio_client:
            self._send_sms(f"[ALGO CRITICAL] {message[:160]}")

    def _send_email(self, subject, body):
        """Send email via SMTP."""
        if not self.email_to or not self.smtp_host or not self.smtp_user or not self.smtp_password:
            # Skip email if credentials not configured
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = ', '.join(self.email_to)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Email sent: {subject}")
        except Exception as e:
            logger.error(f"Email failed: {e}")

    def _send_webhook(self, subject, critical, error, warn, findings):
        """Send Slack-compatible webhook."""
        # SECURITY FIX: Validate webhook URL before sending
        if not self.webhook_url or not _validate_webhook_url(self.webhook_url):
            logger.warning("Webhook URL invalid or not set; skipping webhook send")
            return

        try:
            color = 'danger' if critical > 0 else 'warning'
            text = f"{critical} CRITICAL, {error} ERROR, {warn} WARN"

            finding_text = '\n'.join(
                [f"• {f['severity'].upper()}: {f['check']} ({f['target']})"
                 for f in findings if f['severity'] in ['critical', 'error']][:5]
            )

            payload = {
                'attachments': [{
                    'color': color,
                    'title': subject,
                    'text': text,
                    'fields': [
                        {'title': 'Findings', 'value': finding_text or 'None', 'short': False}
                    ],
                    'ts': int(datetime.now(timezone.utc).timestamp()),
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=get_webhook_timeout())
            logger.info(f"Webhook sent: {subject}")
        except Exception as e:
            logger.error(f"Webhook failed: {e}")

    def _send_webhook_simple(self, title, message, alert_type):
        """Send simple Slack webhook for position alerts."""
        # SECURITY FIX: Validate webhook URL before sending
        if not self.webhook_url or not _validate_webhook_url(self.webhook_url):
            logger.warning("Webhook URL invalid or not set; skipping webhook send")
            return

        try:
            payload = {
                'attachments': [{
                    'color': 'danger',
                    'title': title,
                    'text': message,
                    'fields': [{'title': 'Alert Type', 'value': alert_type, 'short': True}],
                    'ts': int(datetime.now(timezone.utc).timestamp()),
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=get_webhook_timeout())
            logger.info(f"Webhook sent: {title}")
        except Exception as e:
            logger.error(f"Webhook failed: {e}")

    def _send_sms(self, message):
        """Send SMS via Twilio to all configured numbers."""
        if not self.twilio_client or not self.twilio_from:
            return

        for phone in self.phone_numbers:
            try:
                self.twilio_client.messages.create(
                    body=message,
                    from_=self.twilio_from,
                    to=phone
                )
                logger.info(f"SMS sent to {phone}")
            except Exception as e:
                logger.error(f"SMS to {phone} failed: {e}")


if __name__ == '__main__':
    # Test alerts
    am = AlertManager()
    am.send_patrol_alert(
        'PATROL-20260505-120000',
        {'critical': 1, 'error': 2, 'warn': 3, 'info': 10},
        [
            {'check': 'staleness', 'severity': 'critical', 'target': 'price_daily',
             'message': 'Data stale: 9d > 7d threshold'},
            {'check': 'ohlc_sanity', 'severity': 'error', 'target': 'price_daily',
             'message': '5 rows with High < Low (data corruption)'},
        ]
    )
