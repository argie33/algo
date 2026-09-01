#!/usr/bin/env python3
"""Regression tests for scripts/verify_live_trading_readiness.py's alert-delivery checks.

Added 2026-08-31 per PRODUCTION_READINESS_AUDIT_20260831.md Observation 9 and
memory/alert_delivery_chain_traced_verification_gap_20260831.md: notify(strict=True) succeeding
only proves a DB row was written to algo_notifications, never that a human actually received
anything - an AWS SNS email subscription stuck in PendingConfirmation, or a missing/incomplete
SMTP credential, both fail silently in that sense. check_alert_delivery_channels() surfaces both
read-only; send_test_alert() is the one side-effecting check that actually proves delivery works.
"""

from unittest.mock import MagicMock, patch

from scripts.verify_live_trading_readiness import check_alert_delivery_channels, send_test_alert


def _mock_alert_manager(**overrides):
    mgr = MagicMock()
    mgr.noop_mode = False
    mgr.email_to = []
    mgr.smtp_host = None
    mgr.smtp_user = ""
    mgr.smtp_password = ""
    mgr.sns_topic = ""
    for k, v in overrides.items():
        setattr(mgr, k, v)
    return mgr


def test_noop_mode_reports_failure():
    with patch("algo.reporting.alerts.AlertManager", return_value=_mock_alert_manager(noop_mode=True)):
        failures = check_alert_delivery_channels()
    assert len(failures) == 1
    assert "No alert channel configured" in failures[0]


def test_email_configured_with_incomplete_smtp_reports_failure():
    mgr = _mock_alert_manager(email_to=["a@b.com"], smtp_host=None, smtp_user="", smtp_password="")
    with patch("algo.reporting.alerts.AlertManager", return_value=mgr):
        failures = check_alert_delivery_channels()
    assert len(failures) == 1
    assert "SMTP credentials are incomplete" in failures[0]


def test_email_configured_with_complete_smtp_passes():
    mgr = _mock_alert_manager(email_to=["a@b.com"], smtp_host="smtp.example.com", smtp_user="u", smtp_password="p")
    with patch("algo.reporting.alerts.AlertManager", return_value=mgr):
        failures = check_alert_delivery_channels()
    assert failures == []


def test_sns_topic_with_zero_subscriptions_reports_failure():
    mgr = _mock_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:algo-alerts")
    mock_sns_client = MagicMock()
    mock_sns_client.list_subscriptions_by_topic.return_value = {"Subscriptions": []}
    with (
        patch("algo.reporting.alerts.AlertManager", return_value=mgr),
        patch("boto3.client", return_value=mock_sns_client),
    ):
        failures = check_alert_delivery_channels()
    assert len(failures) == 1
    assert "ZERO subscriptions" in failures[0]


def test_sns_subscription_pending_confirmation_reports_failure():
    """The exact gap this whole check exists for: publish() succeeds, nobody's actually
    subscribed yet because they never clicked the confirmation email."""
    mgr = _mock_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:algo-alerts")
    mock_sns_client = MagicMock()
    mock_sns_client.list_subscriptions_by_topic.return_value = {
        "Subscriptions": [
            {"SubscriptionArn": "PendingConfirmation", "Endpoint": "argeropolos@gmail.com"},
        ]
    }
    with (
        patch("algo.reporting.alerts.AlertManager", return_value=mgr),
        patch("boto3.client", return_value=mock_sns_client),
    ):
        failures = check_alert_delivery_channels()
    assert len(failures) == 1
    assert "PendingConfirmation" in failures[0]
    assert "argeropolos@gmail.com" in failures[0]


def test_sns_subscription_confirmed_passes():
    mgr = _mock_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:algo-alerts")
    mock_sns_client = MagicMock()
    mock_sns_client.list_subscriptions_by_topic.return_value = {
        "Subscriptions": [
            {"SubscriptionArn": "arn:aws:sns:us-east-1:123:algo-alerts:real-sub-id", "Endpoint": "a@b.com"},
        ]
    }
    with (
        patch("algo.reporting.alerts.AlertManager", return_value=mgr),
        patch("boto3.client", return_value=mock_sns_client),
    ):
        failures = check_alert_delivery_channels()
    assert failures == []


def test_sns_check_failure_does_not_crash_reports_manual_fallback():
    """If the script itself lacks AWS permissions to check subscriptions, it must not crash -
    it should report the gap and point at the manual aws-cli command instead."""
    mgr = _mock_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:algo-alerts")
    with (
        patch("algo.reporting.alerts.AlertManager", return_value=mgr),
        patch("boto3.client", side_effect=RuntimeError("AccessDenied")),
    ):
        failures = check_alert_delivery_channels()
    assert len(failures) == 1
    assert "aws sns list-subscriptions-by-topic" in failures[0]


def test_send_test_alert_success_reports_no_failure():
    with patch("algo.reporting.notifications.notify") as mock_notify:
        failures = send_test_alert()
    assert failures == []
    mock_notify.assert_called_once()
    assert mock_notify.call_args.kwargs.get("strict") is True


def test_send_test_alert_failure_is_reported_not_raised():
    with patch("algo.reporting.notifications.notify", side_effect=RuntimeError("SMTP connection refused")):
        failures = send_test_alert()
    assert len(failures) == 1
    assert "SMTP connection refused" in failures[0]
