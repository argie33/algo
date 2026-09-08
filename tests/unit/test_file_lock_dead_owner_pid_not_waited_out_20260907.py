"""Regression test for the 2026-09-07 fix: FileLockManager's per-loader lock had no PID/
liveness tracking at all - lock content was just "local-dev|expiry", so a crashed loader's
lock blocked every subsequent acquisition attempt for its full SLA-length TTL (up to 1440min
for prices, 540min for company_info_sec - loaders/loader_timeout_config.py) with no way to
tell it apart from a slow-but-alive run.

Live-reproduced 2026-09-07 during the stock_scores factor/composite sanity audit (goal
session): company_info_sec's lock was held with a valid-looking future expiry, but `tasklist`
showed no company_info_sec process running anywhere - the loader had already crashed/exited
(a concurrent invocation's own log showed it gave up after 4 lock-acquisition retries). This
cascaded to `financial_statements`/`valuations`/`value_quality_growth` all being SKIPPED by
scripts/local_loader_scheduler.py for the rest of that lock's ~9h TTL, blocking the very
reload needed to pick up the annual_row_guard_mass_null_regression fix.

scripts/local_loader_scheduler.py's OWN top-level scheduler lock already solved this identical
problem on 2026-08-17 (see that file's `_pid_alive`/`_lock_owner_info`) - this per-loader lock
never got the same treatment. Fix: record the owning PID in the lock file content
("lock_id|expiry|pid") and treat a lock whose recorded PID is confirmed dead as stale
immediately, regardless of how much of its recorded TTL remains - mirroring the scheduler
lock's fix exactly. Legacy 2-part lock files (no PID) are still handled exactly as before.
"""

import os
import time
from datetime import datetime, timedelta, timezone

from utils.db.local_file_lock import FileLockManager


def _write_lock_file(mgr: FileLockManager, lock_key: str, expiry: datetime, pid: int) -> None:
    lock_file = mgr.lock_dir / f"{lock_key}.lock"
    lock_file.write_text(f"local-dev|{expiry.isoformat()}|{pid}", encoding="utf-8")


def _dead_pid() -> int:
    """A PID essentially guaranteed not to belong to any live process."""
    return 999_999_999


class TestDeadOwnerPidNotWaitedOut:
    def test_is_locked_reports_false_for_dead_owner_despite_future_expiry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=_dead_pid())

        assert mgr.is_locked("company_info_sec") is False

    def test_is_locked_reports_true_for_live_owner(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=os.getpid())

        assert mgr.is_locked("company_info_sec") is True

    def test_acquire_succeeds_immediately_when_recorded_owner_is_dead(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=_dead_pid())

        start = time.time()
        acquired = mgr.acquire("company_info_sec", timeout_seconds=5)
        elapsed = time.time() - start

        assert acquired is True
        assert elapsed < 2, "must not wait out the retry loop for a confirmed-dead owner"

    def test_acquire_blocks_when_recorded_owner_is_alive(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=os.getpid())

        assert mgr.acquire("company_info_sec", timeout_seconds=1) is False

    def test_private_cleanup_removes_dead_owner_lock_despite_future_expiry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=35640, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=_dead_pid())

        mgr._cleanup_expired_locks()

        assert not (mgr.lock_dir / "company_info_sec.lock").exists()

    def test_public_cleanup_removes_dead_owner_lock_despite_future_expiry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=35640, enable_auto_cleanup=False)
        _write_lock_file(mgr, "company_info_sec", datetime.now(timezone.utc) + timedelta(hours=8), pid=_dead_pid())

        deleted = mgr.cleanup_expired_locks(lock_key="company_info_sec", max_age_seconds=1800)

        assert deleted == 1
        assert not (mgr.lock_dir / "company_info_sec.lock").exists()

    def test_legacy_two_part_lock_file_without_pid_still_works(self, tmp_path, monkeypatch):
        """Lock files written before this fix have no third (pid) field - must not raise or
        be misinterpreted as dead-owner."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)
        lock_file = mgr.lock_dir / "legacy.lock"
        lock_file.write_text(
            f"local-dev|{(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}",
            encoding="utf-8",
        )

        assert mgr.is_locked("legacy") is True
        assert mgr.acquire("legacy", timeout_seconds=1) is False

    def test_acquired_lock_content_includes_pid(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)

        assert mgr.acquire("fresh_key", timeout_seconds=1) is True
        content = (mgr.lock_dir / "fresh_key.lock").read_text(encoding="utf-8")
        parts = content.split("|")
        assert len(parts) == 3
        assert int(parts[2]) == os.getpid()
