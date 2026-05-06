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

import os
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def notify(kind, severity, title, message=None, symbol=None, details=None):
    """Write a notification. Severity: info | warning | error | critical.

    Note: algo_notifications table is created by init_database.py (schema as code).
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
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
            except Exception:
                pass

        # Wire SNS for critical/error trading events
        if severity in ('critical', 'error'):
            try:
                _publish_sns(severity, title, message, symbol)
            except Exception:
                pass

        return notif_id
    except Exception as e:
        print(f"  (notify failed: {e})")
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


def _publish_sns(severity, title, message, symbol):
    """Publish critical/error alerts to SNS for SMS/Slack routing.

    SNS topic ARN must be in ALERT_SNS_TOPIC_ARN environment variable.
    Intended for PagerDuty, SMS, or Slack integrations.
    """
    import boto3
    sns_arn = os.getenv('ALERT_SNS_TOPIC_ARN')
    if not sns_arn:
        return
    try:
        sns = boto3.client('sns')
        subject = f"[ALGO {severity.upper()}] {title}"
        body = f"{message or ''}\n\nSymbol: {symbol or 'N/A'}"
        sns.publish(
            TopicArn=sns_arn,
            Subject=subject,
            Message=body,
            MessageAttributes={
                'severity': {'DataType': 'String', 'StringValue': severity},
                'symbol': {'DataType': 'String', 'StringValue': symbol or 'N/A'},
            }
        )
    except Exception as e:
        print(f"  (SNS publish failed: {e})")


def get_unseen(limit=50):
    conn = psycopg2.connect(**DB_CONFIG)
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
    conn = psycopg2.connect(**DB_CONFIG)
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
    _ensure_table()
    print("notifications table ensured.")
    test_id = notify('test', 'info', 'Test notification', 'This is a test.')
    print(f"Test notification id: {test_id}")
    unseen = get_unseen(5)
    for n in unseen:
        print(f"  [{n['severity']}] {n['title']}: {n.get('message', '')}")
