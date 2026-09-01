"""Regression tests: FileAlertLogger is now wired into AlertManager._persist_to_db() and
TradeNotificationService._save_notification() as an always-on redundant alert channel.

BUG FOUND 2026-08-31 (PRODUCTION_READINESS_AUDIT_20260831.md Observation 9; recovered from a
stranded branch onto main 2026-09-01, /goal session - see
risk_min_weight_available_floor_added_20260831 memory entry for the broader pattern): algo/
reporting/alerts_file_fallback.py existed but was never imported anywhere in the repo -
confirmed dead code. Its original design (only log to file "if no email/SNS configured") would
have been the wrong fix anyway: the actual risk is a channel being CONFIGURED but silently
failing to deliver (an SNS subscription stuck in PendingConfirmation still lets sns.publish()
return success with nobody receiving it). A local file write that happens unconditionally,
independent of whether other channels are configured or believed to work, closes that "silent
total blackout" risk without needing any AWS confirmation at all.

These tests pin: (1) the file write happens on every alert, regardless of DB outcome; (2) a
broken/unwritable log directory degrades gracefully rather than crashing AlertManager
construction (this class is constructed unconditionally by phase2/phase3/phase6/patrol - a
crash here would be far worse than the gap it's trying to close); (3) TradeNotificationService
reuses AlertManager's file logger rather than creating a second one.
"""

from unittest.mock import MagicMock, patch

from algo.reporting.alerts import AlertManager
from algo.reporting.alerts_file_fallback import FileAlertLogger
from algo.reporting.notifications import TradeNotificationService


def _make_alert_manager():
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        return AlertManager()


class TestFileAlertLoggerResilience:
    def test_unwritable_log_dir_does_not_raise_on_construction(self):
        """A permissions error creating the directory must degrade gracefully, not crash -
        this is constructed unconditionally inside AlertManager.__init__()."""
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
            file_logger = FileAlertLogger()
        assert file_logger.log_dir is None

    def test_log_alert_no_ops_when_log_dir_unavailable(self):
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
            file_logger = FileAlertLogger()
        result = file_logger.log_alert("trade_entry", "critical", "title", "message", "AAPL")
        assert result == ""

    def test_log_alert_writes_real_line_to_configured_dir(self, tmp_path):
        file_logger = FileAlertLogger(log_dir=str(tmp_path))
        result = file_logger.log_alert("trade_entry", "critical", "Order failed", "detail msg", "AAPL")
        assert result != ""
        written = (tmp_path / result.split("\\")[-1].split("/")[-1]).read_text()
        assert "AAPL" in written
        assert "Order failed" in written
        assert "critical" in written

    def test_env_var_overrides_default_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ALERT_FILE_LOG_DIR", str(tmp_path))
        file_logger = FileAlertLogger()
        assert file_logger.log_dir == tmp_path

    def test_write_failure_after_construction_does_not_raise(self, tmp_path):
        """Directory existed at construction time but the write itself fails later (disk full,
        permissions changed, file locked) - must still degrade gracefully."""
        file_logger = FileAlertLogger(log_dir=str(tmp_path))
        with patch("builtins.open", side_effect=OSError("disk full")):
            result = file_logger.log_alert("trade_entry", "critical", "t", "m")
        assert result == ""


class TestAlertManagerFileLoggerWiring:
    def test_persist_to_db_calls_file_logger(self):
        mgr = _make_alert_manager()
        with (
            patch("algo.reporting.alerts.DatabaseContext"),
            patch.object(mgr, "_file_logger") as mock_file_logger,
        ):
            mgr._persist_to_db(kind="position", severity="critical", title="t", message="m", symbol="AAPL")
        mock_file_logger.log_alert.assert_called_once_with("position", "critical", "t", "m", "AAPL")

    def test_file_logger_still_called_when_db_write_fails(self):
        """The two writes are independent - a DB outage must not skip the file record."""
        mgr = _make_alert_manager()
        with (
            patch("algo.reporting.alerts.DatabaseContext", side_effect=RuntimeError("pool exhausted")),
            patch.object(mgr, "_file_logger") as mock_file_logger,
        ):
            mgr._persist_to_db(kind="position", severity="critical", title="t", message="m")
        mock_file_logger.log_alert.assert_called_once()

    def test_db_write_still_attempted_when_file_logger_raises(self):
        """The two writes are independent in the other direction too - a file-logger exception
        must not skip the DB record."""
        mgr = _make_alert_manager()
        with (
            patch("algo.reporting.alerts.DatabaseContext") as mock_db_ctx,
            patch.object(mgr, "_file_logger") as mock_file_logger,
        ):
            mock_cur = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = mock_cur
            mock_ctx.__exit__.return_value = False
            mock_db_ctx.return_value = mock_ctx
            mock_file_logger.log_alert.side_effect = RuntimeError("unexpected")

            mgr._persist_to_db(kind="position", severity="critical", title="t", message="m")

        assert mock_cur.execute.call_count == 1


class TestTradeNotificationServiceFileLoggerWiring:
    def test_save_notification_uses_alert_manager_file_logger(self):
        with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
            mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
            service = TradeNotificationService(config={"enabled": True})

        with (
            patch("algo.reporting.notifications.DatabaseContext") as mock_db_ctx,
            patch.object(service.alert_manager, "_file_logger") as mock_file_logger,
        ):
            mock_cur = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = mock_cur
            mock_ctx.__exit__.return_value = False
            mock_db_ctx.return_value = mock_ctx

            service._save_notification(kind="trade_entry", severity="info", title="t", message="m", symbol="MSFT")

        mock_file_logger.log_alert.assert_called_once_with("trade_entry", "info", "t", "m", "MSFT")

    def test_file_logger_called_even_when_db_write_raises(self):
        """_save_notification's DB write RAISES on failure (unlike AlertManager's best-effort
        _persist_to_db) - the file write must still have already happened before that raise."""
        with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
            mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
            service = TradeNotificationService(config={"enabled": True})

        with (
            patch("algo.reporting.notifications.DatabaseContext", side_effect=RuntimeError("pool exhausted")),
            patch.object(service.alert_manager, "_file_logger") as mock_file_logger,
        ):
            raised = False
            try:
                service._save_notification(kind="trade_entry", severity="info", title="t", message="m")
            except Exception:
                raised = True

        assert raised is True
        mock_file_logger.log_alert.assert_called_once()
