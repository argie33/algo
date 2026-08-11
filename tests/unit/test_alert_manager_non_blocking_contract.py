"""Regression test: AlertManager's "Non-blocking (logs errors only)" contract must
actually hold for send_position_alert(), critical(), and the shared _persist_to_db()
helper they both call - not just for the specific exception types each narrow except
clause happened to name.

BUG FOUND 2026-08-11: _persist_to_db()'s except clause only caught (psycopg2.DatabaseError,
psycopg2.OperationalError), but json.dumps(details) inside it can raise TypeError for any
non-JSON-serializable value (Decimal, datetime, ...) - entirely plausible for a
RISK_BREACH/DIVERGENCE alert carrying raw dollar amounts, and this codebase's own
established Decimal-handling footgun (see feedback_psycopg2_decimal_arithmetic).
send_position_alert()'s and critical()'s own email branches had the same class of gap:
except (smtplib.SMTPException, RuntimeError, OSError, ConnectionError) instead of a bare
Exception. Most real callers (phase2_circuit_breakers.py, phase3_position_monitor.py,
phase6_exit_execution.py) invoke these with no try/except of their own, trusting the
documented non-blocking contract - an exception outside the narrow tuples would have
propagated and crashed the very circuit-breaker/exit-error phase trying to report it.

Verified via: python -m pytest tests/unit/test_alert_manager_non_blocking_contract.py -v
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.reporting.alerts import AlertManager


def _make_alert_manager(email_to=None, sns_topic=""):
    with patch("algo.reporting.alerts.get_credential_manager") as mock_cred_mgr:
        mock_cred_mgr.return_value.get_smtp_credentials.return_value = None
        mgr = AlertManager()
    mgr.email_to = email_to or []
    mgr.sns_topic = sns_topic
    return mgr


class TestPersistToDbNonBlocking:
    def test_decimal_in_details_does_not_raise(self):
        """The realistic trigger: a details dict carrying a raw dollar amount as Decimal,
        exactly what a RISK_BREACH/DIVERGENCE alert would naturally contain."""
        mgr = _make_alert_manager()
        with patch("algo.reporting.alerts.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = mock_cur
            mock_ctx.__exit__.return_value = False
            mock_db_ctx.return_value = mock_ctx

            # Must not raise
            mgr._persist_to_db(
                kind="position",
                severity="critical",
                title="t",
                message="m",
                details={"pct_down": Decimal("12.5"), "when": __import__("datetime").datetime(2026, 8, 11)},
            )

            # The Decimal/datetime must have been serialized (via default=str), not dropped
            inserted_args = mock_cur.execute.call_args[0][1]
            details_json = inserted_args[5]
            assert details_json is not None
            assert "12.5" in details_json

    def test_non_psycopg2_db_error_does_not_raise(self):
        """A DB-layer exception that isn't a psycopg2 subclass (e.g. a connection-pool
        RuntimeError) must still be swallowed, not just literal psycopg2 errors."""
        mgr = _make_alert_manager()
        with patch("algo.reporting.alerts.DatabaseContext", side_effect=RuntimeError("pool exhausted")):
            mgr._persist_to_db(kind="position", severity="critical", title="t", message="m")


class TestSendPositionAlertNonBlocking:
    def test_unexpected_email_exception_does_not_raise(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_send_email", side_effect=TypeError("unexpected")),
        ):
            mgr.send_position_alert("AAPL", "RISK_BREACH", "test", {"amount": Decimal("500.00")})

    def test_decimal_in_details_end_to_end_through_send_position_alert(self):
        """The full realistic path: send_position_alert() -> _persist_to_db() with a
        Decimal-carrying details dict, exactly like phase2_circuit_breakers.py's
        cb_result.get("pct_down") could plausibly be. Uses the real _persist_to_db (not
        mocked) to prove the fix holds end-to-end, only mocking the DB layer itself."""
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch("algo.reporting.alerts.DatabaseContext") as mock_db_ctx,
            patch.object(mgr, "_send_email"),
        ):
            mock_cur = MagicMock()
            mock_ctx = MagicMock()
            mock_ctx.__enter__.return_value = mock_cur
            mock_ctx.__exit__.return_value = False
            mock_db_ctx.return_value = mock_ctx

            mgr.send_position_alert("AAPL", "RISK_BREACH", "test", {"pct_down": Decimal("-7.25")})


class TestCriticalNonBlocking:
    def test_unexpected_email_exception_does_not_raise(self):
        mgr = _make_alert_manager(email_to=["ops@example.com"])
        with (
            patch.object(mgr, "_persist_to_db"),
            patch.object(mgr, "_send_email", side_effect=TypeError("unexpected")),
        ):
            mgr.critical("something is wrong")
