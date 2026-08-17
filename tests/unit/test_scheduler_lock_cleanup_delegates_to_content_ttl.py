"""Regression test for the 2026-08-17 fix: scripts/local_loader_scheduler.py's own inline
stale-lock cleanup (run at the start of every `--now <pipeline>` invocation) deleted any lock
file older than a flat 5-minute file-age threshold, with no regard for the lock's own recorded
content-based expiry - a second, unpatched copy of the exact bug already fixed once in
utils/db/local_file_lock.py's FileLockManager (commit 676c6c949, see
test_file_lock_long_ttl_not_stolen_by_file_age.py).

Per-loader lock TTLs are tied to real SLA timeouts (up to 1440min for prices, 540min for
company_info_sec - loaders/loader_timeout_config.py), so any loader running past 5 minutes -
i.e. almost every loader on a full universe - had its still-valid lock stolen out from under it
by the *next* scheduler invocation's startup sweep (e.g. a watcher script retrying `--now
signals` every few minutes while `--now reference` is legitimately mid-run).

Live-caught 2026-08-17: this exact sweep deleted sec_segment_info.lock/current_reports_8k.lock/
dividend_data.lock/insider_transaction_velocity.lock out from under the `reference` pipeline
(PID 29036) while it was actively writing sec_segment_info, tripping
"[current_reports_8k] Failed to acquire lock after 4 retries" when the legitimate owner tried to
renew.

Fix: delegate to FileLockManager.cleanup_expired_locks() (already covered by
test_file_lock_long_ttl_not_stolen_by_file_age.py) instead of a third from-scratch
reimplementation of file-age-only cleanup.
"""

import os
import time
from datetime import datetime, timedelta, timezone

from scripts.local_loader_scheduler import _cleanup_stale_lock_files
from utils.db.local_file_lock import FileLockManager


def _write_lock_file(lock_dir, lock_key: str, expiry: datetime, age_seconds: int) -> None:
    lock_file = lock_dir / f"{lock_key}.lock"
    lock_file.write_text(f"local-dev|{expiry.isoformat()}", encoding="utf-8")
    old_time = time.time() - age_seconds
    os.utime(lock_file, (old_time, old_time))


class TestSchedulerStartupCleanupDoesNotStealLongTTLLocks:
    def test_long_ttl_lock_older_than_5min_survives_scheduler_startup_cleanup(self, tmp_path, monkeypatch):
        """A lock file older than the old flat 5-minute threshold but with a content expiry
        still far in the future (e.g. current_reports_8k mid-run) must survive
        _cleanup_stale_lock_files() - the pre-fix version deleted it purely on file age."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        lock_dir = tmp_path / "algo-locks"
        lock_dir.mkdir()

        future_expiry = datetime.now(timezone.utc) + timedelta(hours=2)
        _write_lock_file(lock_dir, "current_reports_8k", future_expiry, age_seconds=600)  # 10 min old

        _cleanup_stale_lock_files()

        assert (lock_dir / "current_reports_8k.lock").exists(), (
            "a lock with a valid, still-future recorded TTL must not be deleted just because "
            "the file itself is older than 5 minutes"
        )

    def test_corrupted_lock_with_no_readable_expiry_still_cleaned_up(self, tmp_path, monkeypatch):
        """No-content-TTL locks (corrupted/crashed mid-write) must still fall back to file age
        cleanup - the fix must not simply stop cleaning up locks altogether."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        lock_dir = tmp_path / "algo-locks"
        lock_dir.mkdir()

        lock_file = lock_dir / "corrupted.lock"
        lock_file.write_text("garbage-no-pipe-separator", encoding="utf-8")
        old_time = time.time() - 2000
        os.utime(lock_file, (old_time, old_time))

        _cleanup_stale_lock_files()

        assert not lock_file.exists()

    def test_delegates_to_file_lock_manager_cleanup_expired_locks(self, monkeypatch):
        """_cleanup_stale_lock_files must call FileLockManager.cleanup_expired_locks() rather
        than reimplementing its own file-age loop - pins the fix's actual mechanism, not just
        its observable behavior, so a future edit can't quietly reintroduce a parallel
        file-age-only sweep."""
        calls = []

        class _FakeMgr:
            def __init__(self, enable_auto_cleanup):
                calls.append(enable_auto_cleanup)

            def cleanup_expired_locks(self):
                calls.append("cleanup_expired_locks_called")
                return 0

        monkeypatch.setattr("scripts.local_loader_scheduler.FileLockManager", _FakeMgr)

        _cleanup_stale_lock_files()

        assert calls == [False, "cleanup_expired_locks_called"], (
            "expected FileLockManager(enable_auto_cleanup=False).cleanup_expired_locks() to be "
            f"called exactly once, got {calls}"
        )


def test_file_lock_manager_still_importable_for_delegation():
    # Sanity check that the delegation target actually exists with the expected interface.
    assert hasattr(FileLockManager, "cleanup_expired_locks")
