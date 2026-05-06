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
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class AlertManager:
    """Send alerts via email and webhook."""

    def __init__(self):
        self.email_from = os.getenv('ALERT_EMAIL_FROM', 'noreply@algo.local')
        self.email_to = [e.strip() for e in os.getenv('ALERT_EMAIL_TO', '').split(',') if e.strip()]
        self.smtp_host = os.getenv('ALERT_SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('ALERT_SMTP_PORT', 587))
        self.smtp_user = os.getenv('ALERT_SMTP_USER', '')
        self.smtp_password = os.getenv('ALERT_SMTP_PASSWORD', '')
        self.webhook_url = os.getenv('ALERT_WEBHOOK_URL', '')

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
                print(f"[ALERT] Twilio init failed: {e}")

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
            f'Data Patrol Alert — {datetime.now().isoformat()}',
            f'Run: {patrol_run_id}',
            '',
            f'Counts:',
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

        # Send email
        if self.email_to:
            self._send_email(subject, body_text)

        # Send SMS
        if self.phone_numbers and self.twilio_client:
            self._send_sms(sms_text)

        # Send webhook (Slack-compatible format)
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
            f'Position Alert — {datetime.now().isoformat()}',
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

    def _send_email(self, subject, body):
        """Send email via SMTP."""
        if not self.email_to:
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = ', '.join(self.email_to)
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            print(f"[ALERT] Email sent: {subject}")
        except Exception as e:
            print(f"[ALERT] Email failed: {e}")

    def _send_webhook(self, subject, critical, error, warn, findings):
        """Send Slack-compatible webhook."""
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
                    'ts': int(datetime.now().timestamp()),
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=5)
            print(f"[ALERT] Webhook sent: {subject}")
        except Exception as e:
            print(f"[ALERT] Webhook failed: {e}")

    def _send_webhook_simple(self, title, message, alert_type):
        """Send simple Slack webhook for position alerts."""
        try:
            payload = {
                'attachments': [{
                    'color': 'danger',
                    'title': title,
                    'text': message,
                    'fields': [{'title': 'Alert Type', 'value': alert_type, 'short': True}],
                    'ts': int(datetime.now().timestamp()),
                }]
            }
            requests.post(self.webhook_url, json=payload, timeout=5)
            print(f"[ALERT] Webhook sent: {title}")
        except Exception as e:
            print(f"[ALERT] Webhook failed: {e}")

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
                print(f"[ALERT] SMS sent to {phone}")
            except Exception as e:
                print(f"[ALERT] SMS to {phone} failed: {e}")


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
