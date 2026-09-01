"""Regression test: TradeNotificationService._send_notification() must convert a real SMTP
send failure into its documented RuntimeError contract, not let it propagate raw.

BUG FOUND 2026-08-31 (same class as the cancel_bracket_orders fix earlier this session;
recovered from a stranded branch onto main 2026-09-01, /goal session - see
risk_min_weight_available_floor_added_20260831 memory entry for the broader pattern):
AlertManager._send_email() raises (smtplib.SMTPException, RuntimeError, OSError,
ConnectionError) on a real send failure - confirmed locally that .env.local's default
ALERT_SMTP_HOST=localhost has nothing listening on port 25 in this dev environment, so a real
send attempt raises ConnectionRefusedError (an OSError subclass). _send_notification's except
clause only caught (psycopg2.DatabaseError, psycopg2.OperationalError) - none of which match -
so a genuine send failure propagated as a raw, unconverted exception instead of the method's
documented RuntimeError. notify()'s own outer `except Exception` masks this when called through
that path, but process_events() calls _send_notification directly with no such outer catch.
"""

from unittest.mock import MagicMock, patch

from algo.reporting.notifications import TradeNotificationService, notify
from algo.trading.exceptions import NotificationError


def _make_service():
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        service = TradeNotificationService(config={"enabled": True})
    service.alert_manager.email_to = ["dev@algo.local"]
    return service


class TestSendNotificationSmtpFailureCaught:
    def test_connection_refused_is_converted_to_runtime_error(self):
        """The exact real-world failure mode: nothing listening at the configured SMTP host."""
        service = _make_service()
        with (
            patch.object(service, "_save_notification"),
            patch.object(service.alert_manager, "_send_email", side_effect=ConnectionRefusedError("refused")),
        ):
            raised_type = None
            try:
                service._send_notification("subject", "message")
            except Exception as e:
                raised_type = type(e)

        assert raised_type is RuntimeError

    def test_smtp_exception_is_converted_to_runtime_error(self):
        import smtplib

        service = _make_service()
        with (
            patch.object(service, "_save_notification"),
            patch.object(service.alert_manager, "_send_email", side_effect=smtplib.SMTPConnectError(111, "refused")),
        ):
            raised_type = None
            try:
                service._send_notification("subject", "message")
            except Exception as e:
                raised_type = type(e)

        assert raised_type is RuntimeError

    def test_no_email_configured_does_not_raise(self):
        """Sanity check: the fix must not turn the healthy no-op path into a failure."""
        service = _make_service()
        service.alert_manager.email_to = []
        with patch.object(service, "_save_notification"):
            service._send_notification("subject", "message")  # must not raise


class TestNotifyOuterCatchStillWorksThroughTheFix:
    def test_notify_strict_true_still_raises_notification_error_on_send_failure(self):
        """End-to-end through the module-level notify() wrapper: a real SMTP failure must
        still surface as NotificationError when strict=True, same contract as before this fix -
        this fix only changes what happens when _send_notification is called directly."""
        with (
            patch("algo.reporting.notifications.TradeNotificationService") as mock_service_cls,
        ):
            mock_service = MagicMock()
            mock_service._send_notification.side_effect = ConnectionRefusedError("refused")
            mock_service_cls.return_value = mock_service

            raised = False
            try:
                notify("critical", "title", "message", strict=True)
            except NotificationError:
                raised = True

        assert raised is True
