#!/usr/bin/env python3
"""File-based lock manager for LOCAL_MODE development.

Provides lock management using filesystem files instead of DynamoDB.
Used in LOCAL_MODE to avoid AWS DynamoDB permissions issues.
"""

import logging
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.db.dynamo_lock import DynamoDBLockManager
    from utils.db.rds_lock import RDSLockManager

logger = logging.getLogger(__name__)


class FileLockManager:
    """File-based lock manager for local development.

    Uses filesystem files for lock management instead of DynamoDB.
    Suitable for LOCAL_MODE development where AWS access is not available.
    """

    def __init__(
        self,
        table_name: str | None = None,
        lock_duration_seconds: int = 300,
        enable_auto_cleanup: bool = True,
    ):
        """Initialize file-based lock manager.

        Args:
            table_name: Unused (for compatibility with DynamoDBLockManager)
            lock_duration_seconds: Lock expiration time (SESSION 107 FIX: changed from 600s to 300s/5min)
            enable_auto_cleanup: Automatically clean expired locks on startup
        """
        self.lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
        self.lock_dir.mkdir(exist_ok=True, parents=True)
        self.lock_duration_seconds = lock_duration_seconds
        self.enable_auto_cleanup = enable_auto_cleanup
        self.current_lock_file: Path | None = None
        self.is_available = True

        logger.info(f"[FILE_LOCK] Using filesystem locks at {self.lock_dir} (duration={lock_duration_seconds}s)")

        if self.enable_auto_cleanup:
            self._cleanup_expired_locks()

    def _cleanup_expired_locks(self) -> None:
        """Remove expired lock files by checking both content timestamp AND file age.

        CRITICAL FIX: Windows file deletion can fail (WinError 32) during __del__ of crashed runs,
        leaving stale locks. Auto-cleanup needs to handle both:
        1. Content-based expiry: Lock has explicit expiry timestamp in content (authoritative -
           each lock file records its own TTL, set from that loader's real SLA timeout).
        2. File-age fallback: ONLY when content can't be read/parsed at all (corrupted or
           malformed lock file) - assume stale after 30min with no readable expiry.

        BUG FIX (2026-08-17): Previously deleted a lock if EITHER content was expired OR the file
        was merely >30min old - even when the file's own recorded expiry was still hours in the
        future. Per-loader lock TTLs are tied to real SLA timeouts (company_info_sec: 540min,
        prices: 1440min - see loaders/loader_timeout_config.py), so any loader running longer
        than 30 minutes had its still-valid lock stolen mid-run by a second concurrent
        invocation, corrupting progress tracking and double-writing data. Live-reproduced
        2026-08-17: company_info_sec's lock (acquired 10:23:04, legitimately held until
        12:16:38) was deleted by this file-age fallback at ~11:something, letting a second
        process acquire the "same" lock 73 minutes in and run concurrently - the two racing
        writers tripped the STATUS_MANAGER's "symbols_loaded cannot decrease" guard repeatedly.
        This mirrors the bug class already fixed twice in orchestrator.py's DB-lock cleanup
        (see algo/orchestration/orchestrator.py's _cleanup_expired_locks docstring) - never
        reconciled here for the filesystem-lock path. Fix: file-age is now only consulted when
        content-based expiry is undeterminable; a lock with a valid, still-future recorded
        expiry is never deleted early regardless of file age.
        """
        try:
            now = datetime.now(timezone.utc)
            # 30-minute fallback threshold, used ONLY when a lock file's content can't be parsed.
            stale_threshold = now - timedelta(seconds=1800)

            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Read expiry time from file content - authoritative when present.
                    expiry_str = None
                    is_content_expired = False
                    try:
                        with open(lock_file, encoding="utf-8") as f:
                            content = f.read().strip()
                            # Format: "lock_id|expiry_timestamp"
                            expiry_str = content.split("|")[1] if "|" in content else None
                            if expiry_str:
                                expiry = datetime.fromisoformat(expiry_str)
                                # CRITICAL FIX: Ensure both datetimes are timezone-aware for comparison
                                if expiry.tzinfo is None:
                                    expiry = expiry.replace(tzinfo=timezone.utc)
                                is_content_expired = now > expiry
                    except Exception as parse_err:
                        logger.debug(
                            f"[FILE_LOCK] Could not parse lock file content, treating as not-expired: {parse_err}"
                        )

                    if expiry_str:
                        # Content had a readable expiry - it alone decides staleness. A valid,
                        # still-future TTL (even one hours long) must never be overridden by
                        # file age, since file age says nothing about this lock's own duration.
                        should_delete = is_content_expired
                        reason = "content_expired"
                    else:
                        # No readable expiry (missing/corrupted content) - fall back to file age.
                        file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)
                        should_delete = file_mtime < stale_threshold
                        reason = "file_age_stale_no_content"

                    if should_delete:
                        lock_file.unlink()
                        logger.debug(f"[FILE_LOCK] Cleaned {reason} lock: {lock_file.name}")
                except Exception as e:
                    logger.warning(f"[FILE_LOCK] Error cleaning lock {lock_file.name}: {e}")
        except Exception as e:
            logger.warning(f"[FILE_LOCK] Cleanup failed: {e}")

    def cleanup_expired_locks(self, lock_key: str | None = None, max_age_seconds: int = 1800) -> int:
        """Public interface for cleaning up stale locks (compatible with DynamoDB/RDS lock managers).

        Args:
            lock_key: Specific lock to clean (unused in FileLockManager - all locks are checked)
            max_age_seconds: Delete locks older than this many seconds from creation

        Returns: Number of locks deleted

        CRITICAL FIX (Session 107): Use file modification time as fallback for locks whose
        content can't be read (parsing failed / missing expiry) - without this, a corrupted
        lock file with no readable expiry would never be deleted.

        BUG FIX (2026-08-17): Session 107's version made file-age the PRIMARY criterion,
        deleting any lock older than max_age_seconds before even checking its own recorded
        TTL. Callers (utils/optimal_loader.py) pass a flat max_age_seconds=1800 (30min) on
        every loader startup, assuming (per that call site's own comment) this "deletes locks
        whose OWN expires_at is 1800s+ in the past" - but the implementation never actually
        checked expires_at first. Per-loader lock TTLs now derive from real SLA timeouts (up to
        1440min for prices, 540min for company_info_sec - loaders/loader_timeout_config.py), so
        any such loader running past 30 minutes had its still-valid lock deleted out from under
        it, letting a second invocation acquire the "same" lock and run concurrently. Live-
        reproduced 2026-08-17 with company_info_sec (see _cleanup_expired_locks() docstring
        above for the full incident). Fix: content-based expiry is now checked FIRST and is
        authoritative when readable; file age is only the deciding factor when content can't be
        parsed at all, and max_age_seconds is only a lower bound on the recorded TTL, never an
        override of it.
        """
        try:
            now = datetime.now(timezone.utc)
            file_age_stale_threshold = now - timedelta(seconds=max_age_seconds)
            deleted_count = 0

            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    expiry_str = None
                    try:
                        with open(lock_file, encoding="utf-8") as f:
                            content = f.read().strip()
                            # Format: "lock_id|expiry_timestamp"
                            expiry_str = content.split("|")[1] if "|" in content else None
                            if expiry_str:
                                expiry = datetime.fromisoformat(expiry_str)
                                if expiry.tzinfo is None:
                                    expiry = expiry.replace(tzinfo=timezone.utc)
                                # Content's own recorded TTL is authoritative - delete only if
                                # it has actually expired, regardless of max_age_seconds/file age.
                                if now > expiry:
                                    lock_file.unlink()
                                    deleted_count += 1
                                    logger.debug(
                                        f"[FILE_LOCK] Cleaned expired-TTL lock: {lock_file.name} "
                                        f"(expiry={expiry.isoformat()} < now={now.isoformat()})"
                                    )
                                continue
                    except Exception as parse_err:
                        logger.debug(f"[FILE_LOCK] Could not parse lock content for {lock_file.name}: {parse_err}")

                    if expiry_str:
                        # Content parsed fine and wasn't expired (handled above) - never fall
                        # through to the file-age heuristic for a lock with a known-valid TTL.
                        continue

                    # No readable expiry at all (missing/corrupted content) - file age is the
                    # only signal available, so fall back to it.
                    file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)
                    if file_mtime < file_age_stale_threshold:
                        lock_file.unlink()
                        deleted_count += 1
                        logger.debug(
                            f"[FILE_LOCK] Cleaned stale lock by file age (no readable content): {lock_file.name} "
                            f"(age={int((now - file_mtime).total_seconds())}s > {max_age_seconds}s)"
                        )

                except Exception as e:
                    logger.warning(f"[FILE_LOCK] Error cleaning lock {lock_file.name}: {e}")

            if deleted_count > 0:
                logger.info(f"[FILE_LOCK] Cleanup: Removed {deleted_count} stale lock(s) older than {max_age_seconds}s")
            return deleted_count
        except Exception as e:
            logger.warning(f"[FILE_LOCK] cleanup_expired_locks failed: {e}")
            return 0

    def is_locked(self, lock_key: str) -> bool:
        """Read-only check: is lock_key currently held by a live (non-expired) lock?

        Never creates, modifies, or deletes anything - safe to call from a caller that just
        wants to know whether to bother attempting its own acquire(). Mirrors the same
        content-based validity check acquire() uses internally (see its lock_is_valid logic)
        so this can't drift out of sync with what acquire() would actually decide.

        ADDED 2026-08-17: phase1_failsafe_retry.py's in-process loader retries had no way to
        tell a table was already being loaded by a concurrently-running scheduler pipeline
        before attempting its own redundant retry - live-confirmed this caused current_reports_8k
        to crash with LockAcquisitionError and forced an operator to manually kill a duplicate
        dividend_data load that was racing the in-flight `reference` pipeline (see that
        function's own retry-loop comment). This lets it skip instead of colliding.
        """
        lock_file = self.lock_dir / f"{lock_key}.lock"
        try:
            with open(lock_file, encoding="utf-8") as f:
                content = f.read().strip()
            parts = content.split("|")
            if len(parts) < 2:
                return False
            expiry = datetime.fromisoformat(parts[1])
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) < expiry
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.debug(f"[FILE_LOCK] is_locked: could not parse {lock_file.name}, assuming unlocked: {e}")
            return False

    def acquire(self, lock_key: str = "orchestrator-run-lock", timeout_seconds: int = 5) -> bool:
        """Acquire file-based lock using atomic file creation.

        CRITICAL FIX (Session 281): Use os.open() with O_CREAT | O_EXCL for atomic lock creation.
        Previous implementation used open(file, "w") which is NOT atomic on Windows.
        Race condition: two processes could both think they acquired the lock.

        CRITICAL FIX (Session 346): Clean up expired locks before checking if one exists.
        Previous: stale lock files from crashed runs blocked subsequent execution indefinitely.
        This ensures expired locks don't block new acquisitions.

        Args:
            lock_key: The lock identifier
            timeout_seconds: How long to retry acquiring lock

        Returns: True if lock acquired, False if another instance holds it
        """
        import errno
        import os

        lock_file = self.lock_dir / f"{lock_key}.lock"

        # CRITICAL: Clean up any expired lock BEFORE checking if another instance holds it
        # This prevents stale locks from crashed runs blocking all subsequent execution
        self._cleanup_expired_locks()

        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout_seconds:
            attempt += 1

            lock_is_valid = False
            try:
                with open(lock_file, encoding="utf-8") as f:
                    content = f.read().strip()
                    # Format: "lock_id|expiry_timestamp"
                    parts = content.split("|")
                    if len(parts) >= 2:
                        expiry_str = parts[1]
                        expiry = datetime.fromisoformat(expiry_str)
                        if datetime.now(timezone.utc) < expiry:
                            lock_is_valid = True
                            logger.debug(f"[FILE_LOCK] Lock held by another instance: {lock_file.name}")
                            if attempt == 1:
                                logger.warning(
                                    f"[LOCK] Another instance already running (lock: {lock_key}). Skipping: {lock_key}"
                                )
            except FileNotFoundError:
                lock_is_valid = False  # Lock file deleted, treat as available
            except Exception as e:
                logger.warning(f"[FILE_LOCK] Error reading lock file: {e}")
                lock_is_valid = False

            if lock_is_valid:
                time.sleep(0.1)
                continue

            # Try to acquire lock with ATOMIC file creation (O_EXCL)
            try:
                now = datetime.now(timezone.utc)
                expiry = now + timedelta(seconds=self.lock_duration_seconds)
                lock_content = f"local-dev|{expiry.isoformat()}"

                # ATOMIC: Only succeeds if file doesn't exist (O_CREAT | O_EXCL)
                # Race-safe: If another process creates file between check and open, we get EEXIST
                try:
                    fd = os.open(str(lock_file), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        f.write(lock_content)
                    self.current_lock_file = lock_file
                    logger.info(f"[FILE_LOCK] Lock acquired (atomic): {lock_file.name}")
                    return True
                except FileExistsError:
                    # Another process won the race - file already exists
                    logger.debug(f"[FILE_LOCK] Another process won lock race for {lock_key}")
                    time.sleep(0.1)
                except OSError as e:
                    if e.errno == errno.EEXIST:  # File already exists (alternate error code)
                        logger.debug(f"[FILE_LOCK] Lock file exists (errno.EEXIST) for {lock_key}")
                        time.sleep(0.1)
                    else:
                        logger.error(f"[FILE_LOCK] OS error acquiring lock: {e}")
                        time.sleep(0.1)

            except Exception as e:
                logger.error(f"[FILE_LOCK] Unexpected error in acquire: {e}")
                time.sleep(0.1)

        logger.warning(f"[FILE_LOCK] Failed to acquire lock after {timeout_seconds}s: {lock_key}")
        return False

    def release(self, lock_key: str = "orchestrator-run-lock") -> bool:
        """Release file-based lock.

        Args:
            lock_key: The lock identifier to release

        Returns: True if lock was released, False otherwise
        """
        lock_file = self.lock_dir / f"{lock_key}.lock"

        try:
            if lock_file.exists():
                # Windows-friendly deletion: file might be locked by another process
                # Retry once with a small delay if it fails (common on Windows)
                try:
                    lock_file.unlink()
                except OSError as e:
                    # WinError 32 = file in use by another process
                    if hasattr(e, "winerror") and e.winerror == 32:
                        # Another process might still be using the file - retry once
                        time.sleep(0.1)
                        try:
                            lock_file.unlink()
                        except OSError:
                            # Still locked - that's OK, it will auto-expire. Just log and continue
                            logger.debug(
                                f"[FILE_LOCK] Could not immediately delete {lock_file.name} (in use by another process), will auto-expire"
                            )
                    else:
                        raise

                if lock_file == self.current_lock_file:
                    self.current_lock_file = None
                logger.info(f"[FILE_LOCK] Lock released: {lock_file.name}")
                return True
        except Exception as e:
            logger.warning(f"[FILE_LOCK] Release error (non-blocking, lock will auto-expire): {e}")

        return False

    def __del__(self) -> None:
        """Clean up lock file on deletion. Best-effort only - don't fail if lock is in use."""
        if self.current_lock_file and self.current_lock_file.exists():
            try:
                self.current_lock_file.unlink()
            except OSError as e:
                # WinError 32 = file in use - OK to ignore, lock will auto-expire
                if hasattr(e, "winerror") and e.winerror == 32:
                    logger.debug(
                        f"[FILE_LOCK] Cleanup: {self.current_lock_file.name} still in use (OK, will auto-expire)"
                    )
                else:
                    logger.debug(f"[FILE_LOCK] Cleanup error (non-critical): {e}")


def get_lock_manager(
    table_name: str | None = None,
    lock_duration_seconds: int = 300,
    enable_auto_cleanup: bool = True,
) -> "FileLockManager | DynamoDBLockManager | RDSLockManager":
    """Factory function that returns a distributed lock manager.

    STRATEGY: LOCAL_MODE (single-machine dev) uses file locks; production uses DynamoDB (with RDS fallback).

    LOCAL_MODE: Use FileLockManager (filesystem-based)
    - Works reliably for single-machine development
    - No database complexity or RDS lock manager bugs
    - Sufficient for dev since only one machine's temp dir is involved

    Production/shared environments: Try DynamoDB first, fall back to RDS
    - DynamoDB: Fastest, distributed-safe, production Lambda
    - RDS: When AWS credentials unavailable (e.g., local without env var)

    SESSION 107 FIX: Changed lock_duration_seconds default from 600s (10m) to 300s (5m).
    This makes crash-lock cleanup more aggressive. With 2x stale threshold, crashed
    locks now expire after ~10 min instead of ~20 min, preventing them from blocking
    subsequent loaders for as long.
    """

    from utils.db.dynamo_lock import DynamoDBLockManager
    from utils.db.rds_lock import RDSLockManager

    local_mode = os.environ.get("LOCAL_MODE", "").lower() == "true"

    # LOCAL_MODE: use filesystem-based locks (simple, reliable for single machine)
    if local_mode:
        logger.info("[LOCK_FACTORY] LOCAL_MODE=true, using FileLockManager (filesystem-based)")
        return FileLockManager(
            table_name=table_name,
            lock_duration_seconds=lock_duration_seconds,
            enable_auto_cleanup=enable_auto_cleanup,
        )

    # Production: try DynamoDB first (preferred for distributed safety)
    try:
        logger.info("[LOCK_FACTORY] Trying DynamoDB locks (preferred for production)")
        lock_mgr: DynamoDBLockManager | RDSLockManager = DynamoDBLockManager(
            table_name=table_name,
            lock_duration_seconds=lock_duration_seconds,
            enable_auto_cleanup=enable_auto_cleanup,
        )
        test_acquired = lock_mgr.acquire(lock_key="__lock_test__", timeout_seconds=1)
        if test_acquired:
            lock_mgr.release(lock_key="__lock_test__")
            logger.info("[LOCK_FACTORY] DynamoDB lock manager available")
            return lock_mgr
        elif lock_mgr.is_available:
            logger.info("[LOCK_FACTORY] DynamoDB lock manager available (contention on test lock)")
            return lock_mgr
    except Exception as e:
        logger.debug(f"[LOCK_FACTORY] DynamoDB initialization/test failed: {e}")

    # DynamoDB unavailable, try RDS fallback
    logger.info("[LOCK_FACTORY] DynamoDB unavailable, falling back to RDS locks")
    try:
        lock_mgr = RDSLockManager(
            table_name=table_name,
            lock_duration_seconds=lock_duration_seconds,
            enable_auto_cleanup=enable_auto_cleanup,
        )
        if lock_mgr.is_available:
            logger.warning("[LOCK_FACTORY] Using RDS fallback for distributed locking")
            return lock_mgr
    except Exception as e:
        logger.debug(f"[LOCK_FACTORY] RDS initialization failed: {e}")

    error_msg = (
        "[LOCK_FACTORY] CRITICAL: Both DynamoDB and RDS lock managers unavailable. "
        "Orchestrator requires distributed locking. "
        "Fix: Either (1) provide AWS credentials for DynamoDB, or (2) ensure RDS is accessible."
    )
    logger.critical(error_msg)
    raise RuntimeError(error_msg)
