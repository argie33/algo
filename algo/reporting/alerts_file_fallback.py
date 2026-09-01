"""File-based alert fallback - an always-on redundant channel, independent of AWS state.

REWORKED 2026-08-31 (PRODUCTION_READINESS_AUDIT_20260831.md Observation 9; recovered from a
stranded branch onto main 2026-09-01 - see risk_min_weight_available_floor_added_20260831 memory
entry for the broader pattern): this module existed but was never imported anywhere (confirmed
via full-repo grep) - genuinely dead code. Its original docstring/`ensure_file_alerts()` gated
file logging on "only if no email/SNS configured", which would have been the wrong design even if
wired in: the actual risk is a channel being CONFIGURED but silently failing to deliver (an SNS
subscription stuck in PendingConfirmation still lets sns.publish() return success). A fallback
gated on "nothing else is configured" would never fire in exactly that scenario. Now wired into
both AlertManager._persist_to_db() and TradeNotificationService._save_notification() as an
unconditional, always-on channel alongside the DB write - not a fallback for when other channels
are absent, but a redundant local record that doesn't depend on AWS confirmation state at all.
"""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FileAlertLogger:
    """Appends every alert to a local daily log file, independent of email/SNS delivery."""

    def __init__(self, log_dir: str | None = None):
        # ALERT_FILE_LOG_DIR lets local dev point this somewhere more discoverable (e.g.
        # "logs/algo_alerts"); default /tmp/algo_alerts is safe everywhere, including AWS
        # Lambda where /tmp is the only writable path (though ephemeral there - useful mainly
        # for the local run_local_orchestrator.py execution path, harmless either way).
        #
        # Construction must never raise: this is a best-effort REDUNDANT channel wired into
        # AlertManager.__init__(), which every phase (circuit breaker, position monitor, exit
        # execution, patrol) constructs unconditionally - a permissions error on some locked-down
        # filesystem creating this class must not crash the entire alerting subsystem for the
        # sake of the extra channel it's trying to add. self.log_dir is None on failure;
        # log_alert() below no-ops rather than retrying the mkdir on every call.
        self.log_dir: Path | None = None
        try:
            resolved_dir: str = log_dir if log_dir else os.getenv("ALERT_FILE_LOG_DIR", "/tmp/algo_alerts")
            candidate = Path(resolved_dir)
            candidate.mkdir(parents=True, exist_ok=True)
            self.log_dir = candidate
        except Exception as e:
            logger.warning(f"[ALERTS] Could not create file-alert log directory: {e}. File alerts disabled.")

    def log_alert(self, kind: str, severity: str, title: str, message: str, symbol: str | None = None) -> str:
        """Write alert to daily log file.

        Args:
            kind: alert kind (trade_entry, trade_exit, position, alert, etc)
            severity: critical, warning, info
            title: alert title
            message: alert details
            symbol: optional symbol

        Returns:
            Path to log file, or "" if the log directory is unavailable or the write failed.
        """
        if self.log_dir is None:
            return ""

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
