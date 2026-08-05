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
        lock_duration_seconds: int = 600,
        enable_auto_cleanup: bool = True,
    ):
        """Initialize file-based lock manager.

        Args:
            table_name: Unused (for compatibility with DynamoDBLockManager)
            lock_duration_seconds: Lock expiration time (default 10 minutes)
            enable_auto_cleanup: Automatically clean expired locks on startup
        """
        self.lock_dir = Path(tempfile.gettempdir()) / "algo-locks"
        self.lock_dir.mkdir(exist_ok=True, parents=True)
        self.lock_duration_seconds = lock_duration_seconds
        self.enable_auto_cleanup = enable_auto_cleanup
        self.current_lock_file: Path | None = None
        self.is_available = True

        logger.info(f"[FILE_LOCK] Using filesystem locks at {self.lock_dir}")

        if self.enable_auto_cleanup:
            self._cleanup_expired_locks()

    def _cleanup_expired_locks(self) -> None:
        """Remove expired lock files."""
        try:
            now = datetime.now(timezone.utc)
            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Read expiry time from file
                    with open(lock_file, encoding="utf-8") as f:
                        content = f.read().strip()
                        # Format: "lock_id|expiry_timestamp"
                        expiry_str = content.split("|")[1] if "|" in content else None
                        if expiry_str:
                            expiry = datetime.fromisoformat(expiry_str)
                            # CRITICAL FIX: Ensure both datetimes are timezone-aware for comparison
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=timezone.utc)
                            if now > expiry:
                                lock_file.unlink()
                                logger.debug(f"[FILE_LOCK] Cleaned expired lock: {lock_file.name}")
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
        """
        try:
            now = datetime.now(timezone.utc)
            cleanup_threshold = now - timedelta(seconds=max_age_seconds)
            deleted_count = 0

            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Read creation/expiry time from file
                    with open(lock_file, encoding="utf-8") as f:
                        content = f.read().strip()
                        # Format: "lock_id|expiry_timestamp"
                        expiry_str = content.split("|")[1] if "|" in content else None
                        if expiry_str:
                            expiry = datetime.fromisoformat(expiry_str)
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=timezone.utc)
                            # Delete if expired OR if created more than max_age_seconds ago
                            # (even if TTL hasn't hit expiration yet)
                            created_time = expiry - timedelta(seconds=self.lock_duration_seconds)
                            if now > expiry or created_time < cleanup_threshold:
                                lock_file.unlink()
                                deleted_count += 1
                                logger.debug(
                                    f"[FILE_LOCK] Cleaned stale lock: {lock_file.name} "
                                    f"(age={int((now - created_time).total_seconds())}s, ttl={self.lock_duration_seconds}s)"
                                )
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
                lock_file.unlink()
                if lock_file == self.current_lock_file:
                    self.current_lock_file = None
                logger.info(f"[FILE_LOCK] Lock released: {lock_file.name}")
                return True
        except Exception as e:
            logger.error(f"[FILE_LOCK] Failed to release lock: {e}")

        return False

    def __del__(self) -> None:
        """Clean up lock file on deletion."""
        if self.current_lock_file and self.current_lock_file.exists():
            try:
                self.current_lock_file.unlink()
            except Exception as e:
                logger.warning(f"[FILE_LOCK] Failed to cleanup lock file {self.current_lock_file}: {e}")


def get_lock_manager(
    table_name: str | None = None,
    lock_duration_seconds: int = 600,
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
