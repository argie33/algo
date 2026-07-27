#!/usr/bin/env python3
"""Regression test for a live log-noise bug in RDSLockManager.acquire() (utils/db/rds_lock.py):

The lock-acquire INSERT relied on catching the UniqueViolation raised when another instance
already holds the lock (the expected, routine outcome of lock contention - that's the whole
point of the retry loop). But DatabaseContext's cursor wrapper (_ErrorLoggedCursor) logs any
DatabaseError at ERROR level with a full traceback *before* rds_lock.py's own try/except gets
a chance to downgrade it to DEBUG. Confirmed live 2026-07-27: a real orchestrator dry-run hit
13 retry attempts against an already-held signal_quality_scores lock and produced 13
ERROR-level tracebacks in the log for completely normal, by-design contention - the exact
"errors in the log for things that aren't errors" pattern this project tries to eliminate.

Fixed to use INSERT ... ON CONFLICT (loader_name) DO NOTHING, which never raises on
contention (still atomic - no TOCTOU race vs a plain check-then-insert). This test locks in
that acquiring an already-held, non-expired lock produces zero ERROR-level log calls.
"""

import logging
from unittest.mock import MagicMock, patch

from utils.db.rds_lock import RDSLockManager


class _FakeLockTable:
    """In-memory stand-in for the loader_execution_locks table."""

    def __init__(self):
        self.rows: dict[str, str] = {}

    def execute(self, query, params=None):
        if query.strip() == "SELECT 1":
            self._last = ("select_1", None)
        elif "DELETE FROM loader_execution_locks WHERE loader_name" in query and "expires_at < NOW()" in query:
            self._last = ("delete_expired", params)
        elif "INSERT INTO loader_execution_locks" in query:
            lock_key, locked_by = params[0], params[1]
            self.rows.setdefault(lock_key, locked_by)  # ON CONFLICT DO NOTHING semantics
            self._last = ("insert", params)
        elif "SELECT locked_by FROM loader_execution_locks" in query:
            lock_key = params[0]
            self._last = ("select", self.rows.get(lock_key))
        else:
            raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        kind, value = self._last
        if kind == "select":
            return (value,) if value is not None else None
        return None


class TestRDSLockContentionNoErrorLog:
    def test_contended_lock_logs_zero_errors(self):
        table = _FakeLockTable()
        table.rows["signal_quality_scores"] = "some-other-worker-id"  # already held

        @property
        def _fake_cursor(self):
            return table

        with (
            patch("utils.db.rds_lock.DatabaseContext") as mock_ctx,
            patch("logging.Logger.error") as mock_error,
        ):
            mock_ctx.return_value.__enter__.return_value = table
            mock_ctx.return_value.__exit__.return_value = False

            manager = RDSLockManager()
            manager.is_available = True
            acquired = manager.acquire("signal_quality_scores", timeout_seconds=0.2)

        assert acquired is False
        assert mock_error.call_count == 0, (
            f"Contended lock acquisition must not log at ERROR level: {mock_error.call_args_list}"
        )
