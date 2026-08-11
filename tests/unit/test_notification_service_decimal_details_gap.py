"""Regression test: TradeNotificationService._save_notification() must not raise (or
silently vanish a governance-critical alert) when a details dict contains a Decimal or
datetime value.

BUG FOUND 2026-08-11: json.dumps(details) had no default=str, so it raised TypeError for
any non-JSON-serializable value - not a psycopg2 exception, so _save_notification's own
except clause didn't catch it, and it propagated as a raw TypeError instead of the
documented RuntimeError contract. Worse, notify()'s own outer `except Exception` (this
module) DOES catch that TypeError - in the default strict=False mode, this reduced a
Decimal in a trade entry/exit alert's details dict to a silently swallowed, log-only
failure with NOT EVEN A DB ROW recorded (algo_notifications never got the INSERT), unlike
algo/reporting/alerts.py's AlertManager (which always persists regardless of email/SNS
outcome). Same fix as that file's equivalent bug: default=str degrades gracefully.

Verified via: python -m pytest tests/unit/test_notification_service_decimal_details_gap.py -v
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.reporting.notifications import TradeNotificationService, notify


def _make_service():
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        return TradeNotificationService(config={"enabled": True})


def test_decimal_in_details_does_not_raise_and_is_persisted():
    service = _make_service()
    with patch("algo.reporting.notifications.DatabaseContext") as mock_db_ctx:
        mock_cur = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False
        mock_db_ctx.return_value = mock_ctx

        # Must not raise
        service._save_notification(
            kind="trade",
            severity="critical",
            title="RISK_BREACH",
            message="test",
            symbol="AAPL",
            details={"pnl": Decimal("-1234.56")},
        )

        inserted_args = mock_cur.execute.call_args[0][1]
        details_json = inserted_args[5]
        assert details_json is not None
        assert "-1234.56" in details_json


def test_notify_strict_false_with_decimal_details_still_persists_to_db():
    """The real-world governance concern: with strict=False (notify()'s default), a
    Decimal in details must not cause the notification to vanish with zero DB trace."""
    with (
        patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr,
        patch("algo.reporting.notifications.DatabaseContext") as mock_db_ctx,
    ):
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        mock_cur = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False
        mock_db_ctx.return_value = mock_ctx

        notify(
            severity="critical",
            title="RISK_BREACH",
            message="test",
            details={"pnl": Decimal("-1234.56")},
        )

        assert mock_cur.execute.called, "notification must still be persisted to algo_notifications"
