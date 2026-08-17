"""Regression test for the 2026-08-17 fix: _check_and_refresh_local()'s retry loop had no way
to tell a table was already being loaded by a concurrently-running scheduler pipeline (e.g.
`reference`) before starting its own in-process retry. loader.run() still acquires the same
FileLockManager per-table lock even when run in-process (the SESSION 94 in-process rewrite only
removed the extra OS process, not the lock acquisition) - live-confirmed 2026-08-17:
current_reports_8k crashed with LockAcquisitionError, and a duplicate dividend_data load raced
the in-flight `reference` pipeline and had to be force-killed by an operator.

Fixed with a read-only FileLockManager.is_locked() peek: if another process already holds the
table's lock, skip this pass's retry instead of colliding - the process already holding it makes
the retry redundant anyway, and the next Phase 1 pass re-checks once it's released.
"""

import datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _StaleOnlyCursor:
    def __init__(self, fresh: datetime.date, stale: datetime.date):
        self._fresh = fresh
        self._stale = stale
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchone(self):
        if "COUNT(*)" in self._last_query:
            if "FROM technical_data_daily" in self._last_query:
                return (100, 100, 100, 100, 100)
            return (100, 100)
        if "FROM etf_price_daily" in self._last_query:
            return (self._stale,)
        return (self._fresh,)


class _StaleOnlyDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _run_with_stale_etf(monkeypatch, mock_import_module, mock_status_mgr_factory, mock_get_lock_manager):
    from algo.orchestrator import phase1_failsafe_retry as mod

    fresh = datetime.date(2026, 8, 10)
    stale = datetime.date(2026, 8, 5)
    cursor = _StaleOnlyCursor(fresh, stale)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _StaleOnlyDatabaseContext(cursor))
    monkeypatch.setattr(mod, "_get_expected_data_date", lambda **kwargs: (fresh, "EOD - test"))
    monkeypatch.setattr(mod, "LoaderStatusManager", mock_status_mgr_factory)
    monkeypatch.setattr("utils.db.local_file_lock.get_lock_manager", mock_get_lock_manager)

    with patch("importlib.import_module", mock_import_module):
        return _check_and_refresh_local(run_date=fresh, pipeline_context="EOD", dry_run=False)


class TestFailsafeRetrySkipsConcurrentlyLockedTable:
    def test_locked_table_skipped_not_retried(self, monkeypatch):
        fake_module = MagicMock()
        fake_module.main = MagicMock(return_value=0)
        fake_module.__name__ = "loaders.load_prices"
        mock_import = MagicMock(return_value=fake_module)
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "FAILED", "completion_pct": 0.0}

        locked_lock_manager = MagicMock()
        locked_lock_manager.is_locked.return_value = True
        mock_get_lock_manager = MagicMock(return_value=locked_lock_manager)

        result = _run_with_stale_etf(monkeypatch, mock_import, lambda table: mock_status_mgr, mock_get_lock_manager)

        assert mock_import.call_count == 0, (
            "must not attempt an in-process retry for a table another process already holds "
            "the lock for - that's the exact collision that crashed current_reports_8k with "
            "LockAcquisitionError and forced an operator to kill a duplicate dividend_data load"
        )
        assert "etf_price_daily" in result["still_failing"]
        assert "etf_price_daily" not in result["recovered"]
        locked_lock_manager.is_locked.assert_called_with("etf_price_daily")

    def test_unlocked_table_still_retried_normally(self, monkeypatch):
        fake_module = MagicMock()
        fake_module.main = MagicMock(return_value=0)
        fake_module.__name__ = "loaders.load_prices"
        mock_import = MagicMock(return_value=fake_module)
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        unlocked_lock_manager = MagicMock()
        unlocked_lock_manager.is_locked.return_value = False
        mock_get_lock_manager = MagicMock(return_value=unlocked_lock_manager)

        result = _run_with_stale_etf(monkeypatch, mock_import, lambda table: mock_status_mgr, mock_get_lock_manager)

        assert mock_import.call_count == 1
        assert "etf_price_daily" in result["recovered"]

    def test_lock_peek_failure_is_non_fatal_and_proceeds_with_retry(self, monkeypatch):
        """If checking lock state itself errors (e.g. lock manager unavailable), the retry must
        still proceed rather than silently dropping every table into still_failing forever."""
        fake_module = MagicMock()
        fake_module.main = MagicMock(return_value=0)
        fake_module.__name__ = "loaders.load_prices"
        mock_import = MagicMock(return_value=fake_module)
        mock_status_mgr = MagicMock()
        mock_status_mgr.get_status.return_value = {"status": "COMPLETED", "completion_pct": 100.0}

        mock_get_lock_manager = MagicMock(side_effect=RuntimeError("lock backend unavailable"))

        result = _run_with_stale_etf(monkeypatch, mock_import, lambda table: mock_status_mgr, mock_get_lock_manager)

        assert mock_import.call_count == 1
        assert "etf_price_daily" in result["recovered"]
