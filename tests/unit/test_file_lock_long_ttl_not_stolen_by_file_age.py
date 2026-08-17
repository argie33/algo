"""Regression test for the 2026-08-17 fix: FileLockManager's file-age fallback (both the
private auto-cleanup in acquire()/__init__ and the public cleanup_expired_locks() called from
utils/optimal_loader.py) deleted lock files older than a flat 30-minute (or caller-supplied
max_age_seconds) threshold even when the lock's own recorded content-based expiry was still
hours in the future.

Per-loader lock TTLs are tied to real SLA timeouts (up to 1440min for prices, 540min for
company_info_sec - see loaders/loader_timeout_config.py), so any loader legitimately running
longer than 30 minutes had its still-valid lock deleted mid-run, letting a second concurrent
invocation acquire the "same" lock and run alongside it - corrupting progress tracking
(STATUS_MANAGER's "symbols_loaded cannot decrease" guard) and double-writing data.

Live-reproduced 2026-08-17: company_info_sec's lock, acquired at 10:23:04 and legitimately held
until 12:16:38 (~113min), was gone by 11:36:39 (~73min in) - well past the 30min file-age
threshold but nowhere near its real ~594min TTL (540min SLA * 1.1 margin).
"""

import time
from datetime import datetime, timedelta, timezone

from utils.db.local_file_lock import FileLockManager


def _write_lock_file(mgr: FileLockManager, lock_key: str, expiry: datetime, age_seconds: int) -> None:
    """Write a lock file with a given recorded expiry, backdated to look `age_seconds` old."""
    lock_file = mgr.lock_dir / f"{lock_key}.lock"
    lock_file.write_text(f"local-dev|{expiry.isoformat()}", encoding="utf-8")
    old_time = time.time() - age_seconds
    import os

    os.utime(lock_file, (old_time, old_time))


class TestLongTTLLockSurvivesFileAgeFallback:
    def test_valid_long_ttl_lock_not_deleted_by_private_cleanup_despite_old_file_age(self, tmp_path, monkeypatch):
        """A lock file older than 30min (file age) but with a content expiry still hours in the
        future (e.g. company_info_sec's ~594min TTL) must survive the auto-cleanup that runs on
        every acquire()/__init__ - the bug deleted it anyway because file-age was OR'd with
        content-expiry instead of only applying when content couldn't be read."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=35640, enable_auto_cleanup=False)

        future_expiry = datetime.now(timezone.utc) + timedelta(seconds=30000)  # still ~8h valid
        _write_lock_file(mgr, "company_info_sec", future_expiry, age_seconds=4400)  # 73 min old

        mgr._cleanup_expired_locks()

        assert (mgr.lock_dir / "company_info_sec.lock").exists(), (
            "lock with a valid, still-future recorded TTL must not be deleted just because the "
            "file itself is older than the flat 30-minute file-age fallback threshold"
        )

    def test_valid_long_ttl_lock_not_deleted_by_public_cleanup_with_flat_max_age(self, tmp_path, monkeypatch):
        """Mirrors utils/optimal_loader.py's real call site: cleanup_expired_locks(lock_key=...,
        max_age_seconds=1800) invoked at loader startup. A lock legitimately 73 minutes into a
        594-minute TTL must not be stolen just because max_age_seconds=1800 (30min) is shorter
        than the lock's own real duration."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=35640, enable_auto_cleanup=False)

        future_expiry = datetime.now(timezone.utc) + timedelta(seconds=30000)
        _write_lock_file(mgr, "company_info_sec", future_expiry, age_seconds=4400)

        deleted = mgr.cleanup_expired_locks(lock_key="company_info_sec", max_age_seconds=1800)

        assert deleted == 0
        assert (mgr.lock_dir / "company_info_sec.lock").exists()

    def test_actually_expired_content_ttl_still_deleted_by_private_cleanup(self, tmp_path, monkeypatch):
        """Content-based expiry must still work: a lock whose own recorded TTL has genuinely
        passed gets cleaned up promptly, regardless of file age."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)

        past_expiry = datetime.now(timezone.utc) - timedelta(seconds=10)
        _write_lock_file(mgr, "short_lock", past_expiry, age_seconds=15)

        mgr._cleanup_expired_locks()

        assert not (mgr.lock_dir / "short_lock.lock").exists()

    def test_corrupted_lock_file_still_falls_back_to_file_age(self, tmp_path, monkeypatch):
        """A lock file with unparseable/missing content (crashed mid-write, corrupted) has no
        authoritative TTL to trust, so the file-age fallback must still apply after 30min."""
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        mgr = FileLockManager(lock_duration_seconds=300, enable_auto_cleanup=False)

        lock_file = mgr.lock_dir / "corrupted.lock"
        lock_file.write_text("garbage-no-pipe-separator", encoding="utf-8")
        import os

        old_time = time.time() - 2000  # older than the 1800s fallback
        os.utime(lock_file, (old_time, old_time))

        mgr._cleanup_expired_locks()

        assert not lock_file.exists(), (
            "a lock file with no readable expiry must still be cleaned up via the file-age "
            "fallback - this fallback exists specifically for corrupted/unparseable lock files"
        )
