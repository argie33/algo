#!/usr/bin/env python3
"""Safeguard alert notification system.

Routes safeguard alerts to multiple channels:
- Logging (always enabled)
- Database (audit trail)
- Email (critical alerts)
- Slack (real-time team notifications)
- SMS (via Twilio for critical margin calls)
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import logging
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, Any, List
from enum import Enum

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logger = logging.getLogger(__name__)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class AlertLevel(Enum):
    """Alert severity levels."""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    CRITICAL = 4


class AlertChannel(Enum):
    """Alert notification channels."""
    LOG = "log"
    DATABASE = "database"
    EMAIL = "email"
    SLACK = "slack"
    SMS = "sms"


class SafeguardAlert:
    """Manages safeguard alerts across multiple channels."""

    def __init__(self, config=None):
        from safeguard_config import get_safeguard_config
        self.config = config or get_safeguard_config()
        self.alerts_enabled = self.config.get('alerts_enabled', True)
        self.channels = self.config.get('alert_channels', ['log', 'database'])

    def send_alert(self, safeguard: str, level: AlertLevel, title: str, message: str,
                   details: Dict[str, Any] = None, symbol: str = None) -> bool:
        """Send alert to all configured channels."""
        if not self.alerts_enabled:
            return False

        alert_data = {
            'timestamp': datetime.now().isoformat(),
            'safeguard': safeguard,
            'level': level.name,
            'title': title,
            'message': message,
            'details': details or {},
            'symbol': symbol,
        }

        success = True

        # Route to each enabled channel
        for channel in self.channels:
            try:
                if channel == 'log':
                    self._send_to_log(alert_data, level)
                elif channel == 'database':
                    self._send_to_database(alert_data)
                elif channel == 'email' and level in (AlertLevel.WARNING, AlertLevel.CRITICAL):
                    self._send_to_email(alert_data)
                elif channel == 'slack' and level == AlertLevel.CRITICAL:
                    self._send_to_slack(alert_data)
                elif channel == 'sms' and level == AlertLevel.CRITICAL:
                    self._send_to_sms(alert_data)
            except Exception as e:
                logger.error(f"Failed to send alert via {channel}: {e}")
                success = False

        return success

    def _send_to_log(self, alert: Dict[str, Any], level: AlertLevel) -> None:
        """Log alert to file."""
        log_level = getattr(logging, level.name)
        logger.log(log_level, f"[{alert['safeguard']}] {alert['title']}: {alert['message']}")

    def _send_to_database(self, alert: Dict[str, Any]) -> None:
        """Persist alert to database for audit trail."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS safeguard_alerts (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    safeguard VARCHAR(50),
                    level VARCHAR(20),
                    title VARCHAR(200),
                    message TEXT,
                    symbol VARCHAR(10),
                    details JSONB,
                    acknowledged BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                INSERT INTO safeguard_alerts
                (timestamp, safeguard, level, title, message, symbol, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                alert['timestamp'],
                alert['safeguard'],
                alert['level'],
                alert['title'],
                alert['message'],
                alert['symbol'],
                str(alert['details']),
            ))

            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to persist alert to database: {e}")

    def _send_to_email(self, alert: Dict[str, Any]) -> None:
        """Send email alert for important events."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            email_to = self.config.get('alert_email')
            if not email_to:
                logger.warning("Email alert configured but no recipient address set")
                return

            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            smtp_user = os.getenv('SMTP_USER', '')
            smtp_pass = os.getenv('SMTP_PASSWORD', '')

            if not smtp_user or not smtp_pass:
                logger.warning("Email alert configured but SMTP credentials not set")
                return

            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = email_to
            msg['Subject'] = f"[{alert['level']}] {alert['title']}"

            body = f"""
Safeguard Alert: {alert['title']}
Level: {alert['level']}
Safeguard: {alert['safeguard']}
Symbol: {alert['symbol'] or 'N/A'}
Time: {alert['timestamp']}

Message:
{alert['message']}

Details:
{str(alert['details'])}
"""
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()

            logger.info(f"Email alert sent to {email_to}")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def _send_to_slack(self, alert: Dict[str, Any]) -> None:
        """Send Slack notification for critical alerts."""
        try:
            import requests

            webhook_url = self.config.get('alert_slack_webhook')
            if not webhook_url:
                logger.warning("Slack alert configured but no webhook URL set")
                return

            payload = {
                'text': f":alert: **{alert['title']}**",
                'blocks': [
                    {
                        'type': 'header',
                        'text': {
                            'type': 'plain_text',
                            'text': f"[{alert['level']}] {alert['title']}",
                        }
                    },
                    {
                        'type': 'section',
                        'fields': [
                            {
                                'type': 'mrkdwn',
                                'text': f"*Safeguard:*\n{alert['safeguard']}"
                            },
                            {
                                'type': 'mrkdwn',
                                'text': f"*Symbol:*\n{alert['symbol'] or 'N/A'}"
                            },
                            {
                                'type': 'mrkdwn',
                                'text': f"*Level:*\n{alert['level']}"
                            },
                            {
                                'type': 'mrkdwn',
                                'text': f"*Time:*\n{alert['timestamp']}"
                            },
                        ]
                    },
                    {
                        'type': 'section',
                        'text': {
                            'type': 'mrkdwn',
                            'text': f"```{alert['message']}```"
                        }
                    }
                ]
            }

            resp = requests.post(webhook_url, json=payload, timeout=5)
            if resp.status_code == 200:
                logger.info("Slack notification sent")
            else:
                logger.warning(f"Slack notification failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")

    def _send_to_sms(self, alert: Dict[str, Any]) -> None:
        """Send SMS alert for critical margin issues."""
        try:
            from twilio.rest import Client

            phone_number = self.config.get('alert_twilio_number')
            account_sid = os.getenv('TWILIO_ACCOUNT_SID', '')
            auth_token = os.getenv('TWILIO_AUTH_TOKEN', '')
            from_number = os.getenv('TWILIO_FROM_NUMBER', '')

            if not all([phone_number, account_sid, auth_token, from_number]):
                logger.warning("SMS alert configured but Twilio credentials not set")
                return

            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=f"[ALGO ALERT] {alert['title']}: {alert['message'][:160]}",
                from_=from_number,
                to=phone_number,
            )

            logger.info(f"SMS sent: {message.sid}")
        except Exception as e:
            logger.error(f"Failed to send SMS alert: {e}")

    def get_recent_alerts(self, hours: int = 24, level: AlertLevel = None) -> List[Dict[str, Any]]:
        """Retrieve recent alerts from database."""
        try:
            conn = psycopg2.connect(**_get_db_config())
            cur = conn.cursor()

            query = """
                SELECT id, timestamp, safeguard, level, title, message, symbol, details
                FROM safeguard_alerts
                WHERE timestamp > NOW() - INTERVAL '%s hours'
            """
            params = [hours]

            if level:
                query += " AND level = %s"
                params.append(level.name)

            query += " ORDER BY timestamp DESC LIMIT 100"

            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            return [
                {
                    'id': row[0],
                    'timestamp': str(row[1]),
                    'safeguard': row[2],
                    'level': row[3],
                    'title': row[4],
                    'message': row[5],
                    'symbol': row[6],
                    'details': row[7],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to retrieve alerts: {e}")
            return []


if __name__ == "__main__":
    alerts = SafeguardAlert()

    # Test alert
    alerts.send_alert(
        safeguard='earnings_blackout',
        level=AlertLevel.CRITICAL,
        title='Earnings Blackout Blocked Entry',
        message='Entry to AAPL blocked due to earnings announcement on 2026-05-15',
        details={'days_until_earnings': 1, 'blackout_window': '±7 days'},
        symbol='AAPL'
    )

    print("Alert sent successfully")
