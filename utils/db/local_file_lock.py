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
        1. Content-based expiry: Lock has explicit expiry timestamp in content
        2. File-age fallback: If lock file is > 30min old, assume it's stale (process crashed)

        SESSION 113 FIX: Changed stale threshold from 2x lock_duration (10min) to 30min.
        Reason: Friday night crashes need to be cleaned up by Saturday morning to prevent
        cascading 2-3 day data staleness (momentum → stability → quality → growth metrics).
        Lock file persisting >10min indicates process is definitely dead (normal runtime <5min).
        """
        try:
            now = datetime.now(timezone.utc)
            # Use 30-minute timeout for stale detection (not 2x lock_duration)
            stale_threshold = now - timedelta(seconds=1800)

            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Check file modification time as fallback for crashed processes
                    file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)
                    is_file_stale = file_mtime < stale_threshold

                    # Read expiry time from file content
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

                    # Remove lock if EITHER content is expired OR file is too old (crashed process)
                    if is_content_expired or is_file_stale:
                        lock_file.unlink()
                        reason = "content_expired" if is_content_expired else "file_age_stale"
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

        CRITICAL FIX (Session 107): Use file modification time as fallback.
        Previous: relied entirely on expiry timestamp in file content. If parsing failed or
        expiry was in the future, lock would never be deleted even if stale (e.g., lock >1h old
        from crashed run). Now: delete if file modification time is older than max_age_seconds,
        providing reliable cleanup for stale locks from crashed processes.
        """
        try:
            now = datetime.now(timezone.utc)
            file_age_stale_threshold = now - timedelta(seconds=max_age_seconds)
            deleted_count = 0

            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Check file modification time as primary indicator of staleness
                    file_mtime = datetime.fromtimestamp(lock_file.stat().st_mtime, tz=timezone.utc)

                    # Use file age as the primary deletion criterion (Session 107 fix)
                    # This handles crashed processes where the lock file persists indefinitely
                    if file_mtime < file_age_stale_threshold:
                        lock_file.unlink()
                        deleted_count += 1
                        logger.debug(
                            f"[FILE_LOCK] Cleaned stale lock by file age: {lock_file.name} "
                            f"(age={int((now - file_mtime).total_seconds())}s > {max_age_seconds}s)"
                        )
                        continue

                    # Secondary check: if lock content has expiry timestamp, delete if expired
                    try:
                        with open(lock_file, encoding="utf-8") as f:
                            content = f.read().strip()
                            # Format: "lock_id|expiry_timestamp"
                            expiry_str = content.split("|")[1] if "|" in content else None
                            if expiry_str:
                                expiry = datetime.fromisoformat(expiry_str)
                                if expiry.tzinfo is None:
                                    expiry = expiry.replace(tzinfo=timezone.utc)
                                # Delete if lock TTL has already expired
                                if now > expiry:
                                    lock_file.unlink()
                                    deleted_count += 1
                                    logger.debug(
                                        f"[FILE_LOCK] Cleaned expired-TTL lock: {lock_file.name} "
                                        f"(expiry={expiry.isoformat()} < now={now.isoformat()})"
                                    )
                    except Exception as parse_err:
                        logger.debug(f"[FILE_LOCK] Could not parse lock content for {lock_file.name}: {parse_err}")

                except Exception as e:
                    logger.warning(f"[FILE_LOCK] Error cleaning lock {lock_file.name}: {e}")

            if deleted_count > 0:
                logger.info(f"[FILE_LOCK] Cleanup: Removed {deleted_count} stale lock(s) older than {max_age_seconds}s")
            return deleted_count
        except Exception as e:
            logger.warning(f"[FILE_LOCK] cleanup_expired_locks failed: {e}")
            return 0

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
