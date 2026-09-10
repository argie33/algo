"""Regression test: AlertManager must page a human (PagerDuty/SMS) for critical events,
independent of and in addition to email/SNS.

REAL-MONEY-READINESS FINDING (2026-09-06 audit): critical alerts (a halt trigger, a failed
stop-loss repair, reconciliation drift) previously only reached email/SNS - fine for
business hours with someone watching an inbox, but nothing would actually wake a human for
an overnight/weekend event. page_critical() closes that gap: opt-in via PAGERDUTY_ROUTING_KEY
or TWILIO_*/ALERT_SMS_TO env vars, no-op silently when unconfigured (same pattern as
email/SNS), and best-effort so a paging failure never blocks the caller's other channels.
"""

from unittest.mock import MagicMock, patch

from algo.reporting.alerts import AlertManager


def _make_alert_manager(**overrides):
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        mock_cred_mgr.return_value.get_paging_credentials.return_value = {}
        mgr = AlertManager()
    mgr.email_to = []
    mgr.sns_topic = ""
    mgr.pagerduty_routing_key = ""
    mgr.sms_to = []
    mgr.twilio_account_sid = ""
    mgr.twilio_auth_token = ""
    mgr.twilio_from_number = ""
    for k, v in overrides.items():
        setattr(mgr, k, v)
    return mgr


class TestPageCriticalNoOpWhenUnconfigured:
    def test_no_channels_configured_makes_no_requests(self) -> None:
        mgr = _make_alert_manager()
        with patch("requests.post") as mock_post:
            mgr.page_critical("subject", "message")
        mock_post.assert_not_called()


class TestPageCriticalPagerDuty:
    def test_configured_routing_key_posts_to_events_api(self) -> None:
        mgr = _make_alert_manager(pagerduty_routing_key="test-routing-key")
        mock_resp = MagicMock(status_code=202)
        mock_resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.page_critical("Halt triggered", "details here")

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://events.pagerduty.com/v2/enqueue"
        assert kwargs["json"]["routing_key"] == "test-routing-key"
        assert kwargs["json"]["payload"]["summary"] == "Halt triggered"
        assert kwargs["json"]["payload"]["severity"] == "critical"

    def test_pagerduty_failure_is_non_blocking(self) -> None:
        mgr = _make_alert_manager(pagerduty_routing_key="test-routing-key")
        with patch("requests.post", side_effect=RuntimeError("network down")):
            mgr.page_critical("subject", "message")  # must not raise


class TestPageCriticalSms:
    def test_configured_twilio_sends_sms_to_each_recipient(self) -> None:
        mgr = _make_alert_manager(
            sms_to=["+15550001111", "+15550002222"],
            twilio_account_sid="AC123",
            twilio_auth_token="tok123",
            twilio_from_number="+15559990000",
        )
        mock_resp = MagicMock(status_code=201)
        mock_resp.raise_for_status.return_value = None
        with patch("requests.post", return_value=mock_resp) as mock_post:
            mgr.page_critical("Halt triggered", "details here")

        assert mock_post.call_count == 2
        first_call_kwargs = mock_post.call_args_list[0].kwargs
        assert first_call_kwargs["data"]["To"] == "+15550001111"
        assert first_call_kwargs["auth"] == ("AC123", "tok123")

    def test_incomplete_twilio_config_sends_nothing(self) -> None:
        # sms_to set but Twilio credentials incomplete - must not attempt a send with
        # missing auth (would just fail loudly against the real Twilio API otherwise).
        mgr = _make_alert_manager(sms_to=["+15550001111"], twilio_account_sid="AC123")
        with patch("requests.post") as mock_post:
            mgr.page_critical("subject", "message")
        mock_post.assert_not_called()

    def test_sms_failure_is_non_blocking(self) -> None:
        mgr = _make_alert_manager(
            sms_to=["+15550001111"],
            twilio_account_sid="AC123",
            twilio_auth_token="tok123",
            twilio_from_number="+15559990000",
        )
        with patch("requests.post", side_effect=RuntimeError("network down")):
            mgr.page_critical("subject", "message")  # must not raise


class TestCriticalMethodPages:
    def test_critical_calls_page_critical(self) -> None:
        mgr = _make_alert_manager()
        with patch.object(mgr, "page_critical") as mock_page:
            mgr.critical("something bad happened")
        mock_page.assert_called_once()


class TestPagingConfiguredFlag:
    """paging_configured is computed at __init__ time from get_paging_credentials()'s
    result - unlike the other tests here, these must mock that return value BEFORE
    construction rather than override attributes after (which would leave the
    already-computed flag stale)."""

    def test_paging_configured_false_when_nothing_set(self) -> None:
        with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
            mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
            mock_cred_mgr.return_value.get_paging_credentials.return_value = {}
            mgr = AlertManager()
        assert mgr.paging_configured is False

    def test_paging_configured_true_with_pagerduty_only(self) -> None:
        with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
            mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
            mock_cred_mgr.return_value.get_paging_credentials.return_value = {"pagerduty_routing_key": "test-key"}
            mgr = AlertManager()
        assert mgr.paging_configured is True
