"""Regression test: Orchestrator._verify_alpaca_account_type and
_verify_database_isolation_level (added in c11cf4f27, "CRITICAL: Add production-readiness
verifications for live trading") had zero test coverage despite being the two checks a same-day
production-readiness audit (PRODUCTION_READINESS_AUDIT_20260831.md) explicitly flagged as "MUST
DO before live money" and marked "IMPLEMENTED & VERIFIED" - the only "verification" on record
was a suggested manual grep of startup logs, not an automated test. Both are fail-closed startup
gates called unconditionally from _run_preflight_checks() with no surrounding try/except, so a
bug here (e.g. an inverted condition) would either silently let execution_mode='auto' trade on
a paper account, or block every single orchestrator run - either failure mode is exactly what
these checks exist to prevent, so they need direct coverage.
"""

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestration.orchestrator import Orchestrator


def _fake_self(config):
    self = object.__new__(Orchestrator)
    self.config = config
    return self


class TestVerifyAlpacaAccountType:
    def test_dry_mode_skips_check(self):
        self = _fake_self({"execution_mode": "dry", "alpaca_paper_trading": None})
        Orchestrator._verify_alpaca_account_type(self)  # must not raise

    def test_review_mode_skips_check(self):
        self = _fake_self({"execution_mode": "review", "alpaca_paper_trading": None})
        Orchestrator._verify_alpaca_account_type(self)  # must not raise

    def test_paper_mode_accepts_any_account_type(self):
        self = _fake_self({"execution_mode": "paper", "alpaca_paper_trading": False})
        Orchestrator._verify_alpaca_account_type(self)  # must not raise

    def test_auto_mode_with_paper_account_raises(self):
        # The exact catastrophic-config case this check exists to catch: real-money mode
        # pointed at the paper endpoint.
        self = _fake_self({"execution_mode": "auto", "alpaca_paper_trading": True})
        with pytest.raises(RuntimeError, match="Mode/Account Type Mismatch"):
            Orchestrator._verify_alpaca_account_type(self)

    def test_auto_mode_with_live_account_passes(self):
        self = _fake_self({"execution_mode": "auto", "alpaca_paper_trading": False})
        Orchestrator._verify_alpaca_account_type(self)  # must not raise

    def test_auto_mode_with_unset_account_type_raises(self):
        # alpaca_paper_trading missing/None must fail closed, not default to either branch.
        self = _fake_self({"execution_mode": "auto", "alpaca_paper_trading": None})
        with pytest.raises(RuntimeError, match="not explicitly set to True or False"):
            Orchestrator._verify_alpaca_account_type(self)

    def test_config_default_alpaca_paper_trading_true_matches_auto_mode_reject(self):
        # self.config.get("alpaca_paper_trading", True) - confirm the documented default
        # (True/paper) actually triggers the auto-mode mismatch when the key is absent
        # entirely, not just when explicitly True.
        self = _fake_self({"execution_mode": "auto"})
        with pytest.raises(RuntimeError, match="Mode/Account Type Mismatch"):
            Orchestrator._verify_alpaca_account_type(self)


class TestVerifyDatabaseIsolationLevel:
    def _run_with_isolation(self, isolation_value):
        self = _fake_self({})
        with patch("algo.orchestration.orchestrator.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = (isolation_value,)
            Orchestrator._verify_database_isolation_level(self)

    def test_read_committed_passes(self):
        self._run_with_isolation("read committed")

    def test_repeatable_read_passes(self):
        self._run_with_isolation("repeatable read")

    def test_serializable_passes(self):
        self._run_with_isolation("serializable")

    def test_case_insensitive_match(self):
        self._run_with_isolation("READ COMMITTED")

    def test_unrecognized_isolation_level_raises(self):
        self = _fake_self({})
        with patch("algo.orchestration.orchestrator.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ("read uncommitted",)
            with pytest.raises(RuntimeError, match="Invalid PostgreSQL isolation level"):
                Orchestrator._verify_database_isolation_level(self)

    def test_empty_result_fails_closed(self):
        self = _fake_self({})
        with patch("algo.orchestration.orchestrator.DatabaseContext") as mock_db:
            mock_cursor = MagicMock()
            mock_db.return_value.__enter__.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            with pytest.raises(RuntimeError, match="Could not verify database isolation level"):
                Orchestrator._verify_database_isolation_level(self)

    def test_db_exception_fails_closed_not_swallowed(self):
        # A connectivity error here must halt startup, not be logged and ignored - this is a
        # CRITICAL safety gate, not observability.
        self = _fake_self({})
        with patch("algo.orchestration.orchestrator.DatabaseContext") as mock_db:
            mock_db.return_value.__enter__.side_effect = psycopg2.OperationalError("connection refused")
            with pytest.raises(RuntimeError, match="Could not verify database isolation level"):
                Orchestrator._verify_database_isolation_level(self)
