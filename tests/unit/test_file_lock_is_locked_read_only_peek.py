"""Regression test for the 2026-08-17 fix: FileLockManager.is_locked() - a read-only peek added
so phase1_failsafe_retry.py's in-process retry loop can tell a table is already being loaded by
a concurrently-running scheduler pipeline before attempting its own redundant retry.

Live-confirmed 2026-08-17: without this check, current_reports_8k crashed with
LockAcquisitionError and a duplicate dividend_data load had to be force-killed by an operator,
both racing the in-flight `reference` pipeline. See phase1_failsafe_retry.py's retry-loop
comment and utils/db/local_file_lock.py's is_locked() docstring for the full incident.
"""

from datetime import datetime, timedelta, timezone

from utils.db.local_file_lock import FileLockManager


def _write_lock_file(mgr: FileLockManager, lock_key: str, expiry: datetime) -> None:
    lock_file = mgr.lock_dir / f"{lock_key}.lock"
    lock_file.write_text(f"local-dev|{expiry.isoformat()}", encoding="utf-8")


class TestIsLockedReadOnlyPeek:
    def test_valid_unexpired_lock_reports_locked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "reference_pipeline_dividend_data", datetime.now(timezone.utc) + timedelta(minutes=30))

        assert mgr.is_locked("reference_pipeline_dividend_data") is True

    def test_expired_lock_reports_unlocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "dividend_data", datetime.now(timezone.utc) - timedelta(seconds=5))

        assert mgr.is_locked("dividend_data") is False

    def test_missing_lock_file_reports_unlocked(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)

        assert mgr.is_locked("never_locked_table") is False

    def test_corrupted_lock_file_reports_unlocked_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        (mgr.lock_dir / "corrupted.lock").write_text("garbage-no-pipe-separator", encoding="utf-8")

        assert mgr.is_locked("corrupted") is False

    def test_never_creates_modifies_or_deletes_the_lock_file(self, tmp_path, monkeypatch):
        """A read-only peek must not mutate lock state - unlike acquire()/cleanup, calling it
        must have zero side effects on disk."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        expiry = datetime.now(timezone.utc) + timedelta(minutes=30)
        _write_lock_file(mgr, "current_reports_8k", expiry)
        lock_file = mgr.lock_dir / "current_reports_8k.lock"
        before = lock_file.read_text(encoding="utf-8")
        before_mtime = lock_file.stat().st_mtime

        mgr.is_locked("current_reports_8k")

        assert lock_file.read_text(encoding="utf-8") == before
        assert lock_file.stat().st_mtime == before_mtime
