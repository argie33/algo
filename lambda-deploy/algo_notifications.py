#!/usr/bin/env python3
"""
Notifications System — surface CRITICAL events to the UI

Writes to algo_notifications table whenever something needs attention:
  - Circuit breaker fires
  - Patrol finds CRITICAL/ERROR severity
  - Trade entry / exit
  - Drawdown threshold crossed
  - Tier transition (e.g., healthy_uptrend -> caution)
  - Position monitor flags >= 2

The UI polls /api/algo/notifications and displays as toast/banner.
Optional email sending when EMAIL_RECIPIENT env is set.

Usage from other modules:
    from algo_notifications import notify
    notify(
        kind='circuit_breaker',
        severity='critical',
        title='Trading Halted',
        message='Drawdown 22% >= 20% threshold',
        symbol=None,
    )
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


def notify(kind, severity, title, message=None, symbol=None, details=None):
    """Write a notification. Severity: info | warning | error | critical.

    Note: algo_notifications table is created by init_database.py (schema as code).
    Fallback: if DB fails, attempt direct AlertManager send.
    """
    import logging
    logger = logging.getLogger(__name__)

    notif_id = None
    try:
        conn = psycopg2.connect(**_get_db_config())
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO algo_notifications (kind, severity, title, message, symbol, details)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
            (kind, severity, title, message, symbol,
             json.dumps(details) if details else None),
        )
        notif_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # Optional: send email if configured
        recipient = os.getenv('EMAIL_RECIPIENT')
        if recipient and severity in ('critical', 'error'):
            try:
                _send_email(recipient, severity, title, message, symbol)
            except Exception as e:
                logger.warning(f"Email send failed: {e}")

        return notif_id
    except Exception as e:
        logger.error(f"notify() DB write failed: {e}. Attempting AlertManager fallback.")

        # Fallback: send via AlertManager if DB is down
        try:
            from algo_alerts import AlertManager
            alerts = AlertManager()
            alerts.send_patrol_alert(
                f'notification_{kind}',
                {severity: 1},
                [{'severity': severity, 'check': kind, 'target': symbol or 'system', 'message': f'{title}: {message}'}]
            )
            logger.info(f"Fallback AlertManager notification sent for {kind}")
        except Exception as e2:
            logger.critical(f"Both notify() and AlertManager fallback failed: {e2}")

        return None


def _send_email(recipient, severity, title, message, symbol):
    """Optional SMTP email — only if EMAIL_RECIPIENT env is configured."""
    smtp_host = os.getenv('SMTP_HOST')
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASS')
    if not (smtp_host and smtp_user and smtp_pass):
        return
    import smtplib
    from email.mime.text import MIMEText
    msg = MIMEText(f"{message or ''}\n\nSymbol: {symbol or 'N/A'}\nSeverity: {severity}")
    msg['Subject'] = f"[ALGO {severity.upper()}] {title}"
    msg['From'] = smtp_user
    msg['To'] = recipient
    with smtplib.SMTP_SSL(smtp_host, 465) as smtp:
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(msg)


def get_unseen(limit=50):
    conn = psycopg2.connect(**_get_db_config())
    cur = conn.cursor()
    cur.execute(
        """SELECT id, kind, severity, title, message, symbol, details, created_at
           FROM algo_notifications
           WHERE seen = FALSE
           ORDER BY
               CASE severity
                   WHEN 'critical' THEN 1
                   WHEN 'error' THEN 2
                   WHEN 'warning' THEN 3
                   ELSE 4
               END,
               created_at DESC
           LIMIT %s""",
        (limit,),
    )
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    notifications = [dict(zip(cols, row)) for row in rows]
    cur.close()
    conn.close()
    return notifications


def mark_seen(notification_ids):
    conn = psycopg2.connect(**_get_db_config())
    cur = conn.cursor()
    cur.execute(
        """UPDATE algo_notifications SET seen = TRUE, seen_at = CURRENT_TIMESTAMP
           WHERE id = ANY(%s)""",
        (notification_ids,),
    )
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    test_id = notify('test', 'info', 'Test notification', 'This is a test.')
    print(f"Test notification id: {test_id}")
    unseen = get_unseen(5)
    for n in unseen:
        print(f"  [{n['severity']}] {n['title']}: {n.get('message', '')}")
