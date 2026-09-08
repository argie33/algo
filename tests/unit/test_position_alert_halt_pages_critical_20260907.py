"""Regression test: send_position_alert() must classify HALT_FLAG_ACTIVE as critical and
must actually call page_critical() for critical alerts.

BUG FOUND 2026-09-07 (real-money-readiness audit): halt_flag_manager.py's
_alert_halt_detected() calls send_position_alert("PORTFOLIO", "HALT_FLAG_ACTIVE", ...) every
time any phase finds an active halt - arguably the single most operator-actionable state
this system can be in. send_position_alert()'s severity classification only checked for
"CRITICAL"/"BLOCK" substrings in alert_type, so "HALT_FLAG_ACTIVE" was always classified
"warning". Worse, unlike the sibling send_data_patrol_alert() method, send_position_alert()
never called page_critical() at all, for any severity - so even a genuinely CRITICAL/BLOCK
position alert could never reach PagerDuty/Twilio, only email/SNS.
"""

from unittest.mock import MagicMock, patch

from algo.reporting.alerts import AlertManager


def _make_alert_manager():
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        mock_cred_mgr.return_value.get_paging_credentials.return_value = {}
        mgr = AlertManager()
    mgr.email_to = []
    mgr.sns_topic = ""
    return mgr


class TestSendPositionAlertPaging:
    def test_halt_flag_active_classified_critical_and_pages(self):
        mgr = _make_alert_manager()
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "page_critical") as mock_page,
        ):
            mgr.send_position_alert("PORTFOLIO", "HALT_FLAG_ACTIVE", "Halt detected")

        assert mock_persist.call_args.kwargs["severity"] == "critical"
        mock_page.assert_called_once()

    def test_non_critical_alert_type_does_not_page(self):
        mgr = _make_alert_manager()
        with (
            patch.object(mgr, "_persist_to_db") as mock_persist,
            patch.object(mgr, "page_critical") as mock_page,
        ):
            mgr.send_position_alert("AAPL", "DIVERGENCE", "Minor divergence")

        assert mock_persist.call_args.kwargs["severity"] == "warning"
        mock_page.assert_not_called()

    def test_critical_and_block_alert_types_still_page(self):
        mgr = _make_alert_manager()
        for alert_type in ("RISK_BREACH_CRITICAL", "ENTRY_BLOCKED"):
            with (
                patch.object(mgr, "_persist_to_db") as mock_persist,
                patch.object(mgr, "page_critical") as mock_page,
            ):
                mgr.send_position_alert("AAPL", alert_type, "message")
            assert mock_persist.call_args.kwargs["severity"] == "critical"
            mock_page.assert_called_once()
