#!/usr/bin/env python3
"""
Alert Escalation - Notify on critical data/trading issues

Sends emails + SNS alerts when patrol finds critical/error issues.
Configuration via environment variables:
  ALERT_EMAIL_FROM: sender address
  ALERT_EMAIL_TO: comma-separated recipients
  ALERT_SMTP_HOST, ALERT_SMTP_PORT, ALERT_SMTP_USER, ALERT_SMTP_PASSWORD
  ALERTS_SNS_TOPIC: optional SNS topic ARN for alerts
"""

import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import psycopg2

from algo.config.credential_manager import get_credential_manager
from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class AlertManager:
    """Send alerts via email, SNS, and a durable database record.

    Every alert is always persisted to algo_notifications (the table the dashboard already
    surfaces), regardless of configuration. If no email/SNS channel is configured, external
    delivery is skipped ("no-op mode" for that part only) - this allows paper trading and
    testing without external alert infrastructure while still guaranteeing every critical
    safety event leaves a durable, queryable trace.
    """

    def __init__(self) -> None:
        self.email_from = os.getenv("ALERT_SMTP_FROM", os.getenv("ALERT_EMAIL_FROM", "noreply@algo.local"))
        self.email_to = [e.strip() for e in os.getenv("ALERT_EMAIL_TO", "").split(",") if e.strip()]

        # CRITICAL FIX: previously read raw os.getenv("ALERT_SMTP_HOST"/"ALERT_SMTP_USER"/
        # "ALERT_SMTP_PASSWORD") directly - but terraform/modules/services/main.tf stores
        # these in AWS Secrets Manager and sets ALERT_SMTP_SECRET_ARN on the Lambda env,
        # deliberately NOT ALERT_SMTP_PASSWORD (security fix: env vars are visible via
        # lambda:GetFunction). No code anywhere ever consumed ALERT_SMTP_SECRET_ARN, so in
        # the real deployed Lambda self.smtp_password was always empty even with everything
        # correctly configured in terraform/IAM, silently disabling email alerts. Route
        # through get_smtp_credentials(), which fetches the Secrets Manager blob when
        # ALERT_SMTP_SECRET_ARN is set (AWS) or falls back to the individual env vars
        # (local dev).
        try:
            smtp_creds = get_credential_manager().get_smtp_credentials()
        except (ValueError, RuntimeError) as e:
            logger.warning(f"[ALERT CONFIG] SMTP credential lookup failed: {e}. Email alerts disabled.")
            smtp_creds = None

        if smtp_creds:
            self.smtp_host: str | None = smtp_creds["host"]
            self.smtp_port = smtp_creds["port"]
            self.smtp_user = smtp_creds["username"]
            self.smtp_password = smtp_creds["password"]
        else:
            self.smtp_host = None
            self.smtp_port = int(os.getenv("ALERT_SMTP_PORT", "587"))
            self.smtp_user = ""
            self.smtp_password = ""

        if self.email_to and not (self.smtp_host and self.smtp_user and self.smtp_password):
            logger.warning(
                "Email alerts configured but SMTP credentials incomplete. "
                "Set ALERT_SMTP_HOST, ALERT_SMTP_USER, ALERT_SMTP_PASSWORD to enable email."
            )
            self.email_to = []

        self.sns_topic = os.getenv("ALERTS_SNS_TOPIC", "")
        self._sns_client = None

        # Allow no-op mode if no alert channels configured (for paper trading / testing).
        # CRITICAL: "no-op" only applies to EXTERNAL delivery (email/SNS) - every alert is
        # still persisted to algo_notifications (see _persist_to_db) regardless of this flag.
        # Previously "no-op" meant "does literally nothing" - send_position_alert/critical/
        # send_patrol_alert/send_loader_alert all early-returned before any write of any kind,
        # so a circuit breaker trip, exit failure, or Phase 9 governance halt with no email/SNS
        # configured left zero durable trace anywhere, not even a database row the dashboard
        # could surface. External delivery still requires real credentials (that part is a
        # deployment/config task, not something to fix in code) but the record itself no
        # longer depends on having them.
        self.noop_mode = not (self.email_to or self.sns_topic)
        if self.noop_mode:
            logger.warning(
                "[ALERT CONFIG] No alert channels configured - email/SNS delivery disabled, "
                "still persisting all alerts to algo_notifications. "
                "Configure ALERT_EMAIL_TO + ALERT_SMTP_* (email) or ALERTS_SNS_TOPIC (SNS) for external delivery."
            )

    def _persist_to_db(
        self,
        kind: str,
        severity: str,
        title: str,
        message: str,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Persist an alert to algo_notifications regardless of email/SNS configuration.

        Best-effort: a DB error here must not prevent the caller's own alert logic (which
        already has its own error handling for email/SNS) from proceeding - logging the
        failure is the correct behavior, not raising, since these call sites are documented
        as non-blocking elsewhere in this file.
        """
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
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[ALERTS] Failed to persist alert to algo_notifications: {e}. Title: {title}")

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

    def send_patrol_alert(
        self, patrol_run_id: str, counts: dict[str, int], flagged_findings: list[dict[str, str]]
    ) -> None:
        """Send CRITICAL alert when patrol finds issues. Fails hard on send failure.

        Args:
            patrol_run_id: ID of patrol run
            counts: dict with keys 'critical', 'error', 'warn', 'info'
            flagged_findings: list of finding dicts with keys check, severity, target, message

        Raises:
            RuntimeError: If alert sending fails for any configured channel
        """
        required_count_keys = ["critical", "error", "warn"]
        for key in required_count_keys:
            if key not in counts:
                raise ValueError(
                    f"[ALERTS] Missing required count key '{key}' in alert counts dict. "
                    f"Available keys: {list(counts.keys())}. Cannot assess alert severity without all count metrics."
                )
        critical = counts["critical"]
        error = counts["error"]
        warn = counts["warn"]

        # Only alert on CRITICAL or ERROR (not WARN)
        if critical == 0 and error == 0:
            return

        severity = "CRITICAL" if critical > 0 else "ERROR"
        subject = f"[ALGO ALERT] {severity}: Data Patrol {patrol_run_id}"

        # Build email body
        body_lines = [
            f"Data Patrol Alert - {datetime.now(timezone.utc).isoformat()}",
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

        self._persist_to_db(
            kind="patrol",
            severity=severity.lower(),
            title=subject,
            message=body_text,
            details={"patrol_run_id": patrol_run_id, "counts": counts},
        )

        # Data patrol alerts are CRITICAL - they must reach ops or trading should halt.
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

        if send_errors:
            raise RuntimeError(
                f"[CRITICAL] Data patrol alert send failed for run {patrol_run_id}: {'; '.join(send_errors)}. "
                "Ops team may not have received notification of critical data issues."
            )

    def send_position_alert(
        self, symbol: str, alert_type: str, message: str, details: dict[str, object] | None = None
    ) -> None:
        """Send alert for position-related issues. Non-blocking (logs errors only).

        Args:
            symbol: stock symbol
            alert_type: 'STUCK_ORDER', 'DIVERGENCE', 'RISK_BREACH', etc.
            message: human-readable message
            details: optional dict with extra context
        """
        subject = f"[ALGO ALERT] {alert_type}: {symbol}"
        body_lines = [
            f"Position Alert - {datetime.now(timezone.utc).isoformat()}",
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

        self._persist_to_db(
            kind="position",
            severity="critical" if "CRITICAL" in alert_type.upper() or "BLOCK" in alert_type.upper() else "warning",
            title=subject,
            message=body_text,
            symbol=symbol,
            details=details if isinstance(details, dict) else None,
        )

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
            f"Loader Health Alert - {datetime.now(timezone.utc).isoformat()}",
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

        self._persist_to_db(
            kind="loader",
            severity=severity.lower(),
            title=subject,
            message=body_text,
            details={"findings": [{"severity": s, "check": c, "message": m} for s, c, m in findings]},
        )

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

    def critical(self, message: str) -> None:
        """Send a generic critical alert. Non-blocking.

        Args:
            message: Alert message
        """
        subject = "[ALGO ALERT] CRITICAL"
        body_text = f"Critical Alert - {datetime.now(timezone.utc).isoformat()}\n\n{message}"

        self._persist_to_db(kind="general", severity="critical", title=subject, message=body_text)

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
