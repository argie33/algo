"""File-based alert fallback for local/testing environments.

Persists trade and system alerts to rotating daily log files so user can monitor
without external email/SNS configuration.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileAlertLogger:
    """Log alerts to local file for monitoring when email/SNS not configured."""

    def __init__(self, log_dir: str = "/tmp/algo_alerts"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_alert(self, kind: str, severity: str, title: str, message: str, symbol: str | None = None) -> str:
        """Write alert to daily log file.

        Args:
            kind: alert kind (trade_entry, trade_exit, position, alert, etc)
            severity: critical, warning, info
            title: alert title
            message: alert details
            symbol: optional symbol

        Returns:
            Path to log file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"algo_alerts_{today}.log"

        timestamp = datetime.now().isoformat()
        line = f"[{timestamp}] {severity:8} {kind:15} {symbol or '':6} {title} - {message}\n"

        try:
            with open(log_file, "a") as f:
                f.write(line)
            return str(log_file)
        except Exception as e:
            logger.error(f"Failed to write alert to file: {e}")
            return ""


def ensure_file_alerts() -> Optional["FileAlertLogger"]:
    """Initialize file-based alert logging if external channels not configured."""

    # Only add file alerts if no external channels configured
    if not os.getenv("ALERT_EMAIL_TO") and not os.getenv("ALERTS_SNS_TOPIC"):
        logger.info("[ALERTS] No email/SNS configured. Using file-based alerts at /tmp/algo_alerts/")
        return FileAlertLogger()
    return None
