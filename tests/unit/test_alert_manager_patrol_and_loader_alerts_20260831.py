"""Coverage test for AlertManager.send_patrol_alert()/send_loader_alert() - found 2026-08-31
via the same objective coverage-analysis pass as commits 5b4ae35ce/8e3479e5d/d242f84aa/79ed3b3/
8cc21ce70/c39561ac1 to have zero dedicated tests despite being the human-notification path for
exactly the scenarios this session's own audits kept discussing: data patrol findings and loader
failures. send_position_alert()/critical()'s "non-blocking" contract already has tests
(test_alert_manager_non_blocking_contract.py) - send_patrol_alert() is deliberately the ONE
alert method in this file that "Fails hard on send failure" (per its own docstring), a real
behavioral difference from its siblings worth locking in explicitly.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.reporting.alerts import AlertManager


def _make_alert_manager(email_to=None, sns_topic=""):
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        # Explicit {} (not the MagicMock default) - a truthy auto-mocked return value here
        # would make page_critical() (added 2026-09-06, called from send_patrol_alert() for
        # CRITICAL severity) attempt a real network call to PagerDuty/Twilio from this test.
        mock_cred_mgr.return_value.get_paging_credentials.return_value = {}
        mgr = AlertManager()
    mgr.email_to = email_to or []
    mgr.sns_topic = sns_topic
    return mgr


class TestSendPatrolAlert:
    def test_no_alert_sent_when_zero_critical_and_zero_error(self):
        """WARN-only findings must not trigger an alert - only CRITICAL/ERROR do."""
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email") as mock_email,
        ):
            mgr.send_patrol_alert("run-1", {"critical": 0, "error": 0, "warn": 5, "info": 10}, [])
        mock_persist.assert_not_called()
        mock_email.assert_not_called()

    def test_raises_on_missing_required_count_key(self):
        mgr = _make_alert_manager()
        with pytest.raises(ValueError, match="critical"):
            mgr.send_patrol_alert("run-1", {"error": 1, "warn": 0}, [])

    def test_sends_email_and_persists_on_critical_count(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email") as mock_email,
        ):
            mgr.send_patrol_alert("run-1", {"critical": 2, "error": 0, "warn": 3}, [])
        mock_persist.assert_called_once()
        assert mock_persist.call_args.kwargs["severity"] == "critical"
        mock_email.assert_called_once()

    def test_severity_is_error_not_critical_when_only_errors_present(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email"),
        ):
            mgr.send_patrol_alert("run-1", {"critical": 0, "error": 3, "warn": 0}, [])
        assert mock_persist.call_args.kwargs["severity"] == "error"

    def test_raises_when_email_send_fails_fail_hard_contract(self):
        """The one deliberate exception to this file's usual non-blocking contract - patrol
        alerts must reach ops or trading should halt, per the function's own docstring."""
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_send_email", side_effect=RuntimeError("smtp down")),
        ):
            with pytest.raises(RuntimeError, match="alert send failed"):
                mgr.send_patrol_alert("run-1", {"critical": 1, "error": 0, "warn": 0}, [])

    def test_raises_when_sns_publish_fails(self):
        mgr = _make_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:topic")
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_publish_sns", side_effect=RuntimeError("sns down")),
        ):
            with pytest.raises(RuntimeError, match="alert send failed"):
                mgr.send_patrol_alert("run-1", {"critical": 1, "error": 0, "warn": 0}, [])

    def test_does_not_raise_when_at_least_one_channel_configured_and_succeeds(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"], sns_topic="arn:aws:sns:us-east-1:123:topic")
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_send_email"),
            patch.object(mgr, "_publish_sns"),
        ):
            mgr.send_patrol_alert("run-1", {"critical": 1, "error": 0, "warn": 0}, [])

    def test_includes_flagged_findings_in_persisted_message(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        findings = [{"check": "price_gap", "severity": "critical", "target": "AAPL", "message": "40% gap"}]
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email"),
        ):
            mgr.send_patrol_alert("run-1", {"critical": 1, "error": 0, "warn": 0}, findings)
        message = mock_persist.call_args.kwargs["message"]
        assert "AAPL" in message
        assert "price_gap" in message


class TestSendLoaderAlert:
    def test_no_alert_sent_when_no_critical_or_error_findings(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email") as mock_email,
        ):
            mgr.send_loader_alert([("WARN", "price_daily", "slightly stale")])
        mock_persist.assert_not_called()
        mock_email.assert_not_called()

    def test_sends_alert_on_critical_finding(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email") as mock_email,
        ):
            mgr.send_loader_alert([("CRITICAL", "price_daily", "loader failed")])
        mock_persist.assert_called_once()
        assert mock_persist.call_args.kwargs["severity"] == "critical"
        mock_email.assert_called_once()

    def test_severity_is_error_when_only_error_findings_present(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email"),
        ):
            mgr.send_loader_alert([("ERROR", "buy_sell_daily", "stale")])
        assert mock_persist.call_args.kwargs["severity"] == "error"

    def test_is_non_blocking_email_failure_does_not_raise(self):
        """Unlike send_patrol_alert(), this method's own docstring says 'Non-blocking' -
        a send failure must be swallowed, not propagated."""
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_send_email", side_effect=RuntimeError("smtp down")),
        ):
            mgr.send_loader_alert([("CRITICAL", "price_daily", "loader failed")])

    def test_is_non_blocking_sns_failure_does_not_raise(self):
        mgr = _make_alert_manager(sns_topic="arn:aws:sns:us-east-1:123:topic")
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_publish_sns", side_effect=RuntimeError("sns down")),
        ):
            mgr.send_loader_alert([("CRITICAL", "price_daily", "loader failed")])

    def test_includes_both_critical_and_error_findings_in_message(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        findings = [
            ("CRITICAL", "price_daily", "loader crashed"),
            ("ERROR", "buy_sell_daily", "generation failed"),
        ]
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "_send_email"),
        ):
            mgr.send_loader_alert(findings)
        message = mock_persist.call_args.kwargs["message"]
        assert "price_daily" in message
        assert "buy_sell_daily" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
