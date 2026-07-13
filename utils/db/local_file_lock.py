#!/usr/bin/env python3
"""File-based lock manager for LOCAL_MODE development.

Provides lock management using filesystem files instead of DynamoDB.
Used in LOCAL_MODE to avoid AWS DynamoDB permissions issues.
"""

import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.db.dynamo_lock import DynamoDBLockManager

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
            now = datetime.utcnow()
            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    # Read expiry time from file
                    with open(lock_file, encoding="utf-8") as f:
                        content = f.read().strip()
                        # Format: "lock_id|expiry_timestamp"
                        expiry_str = content.split("|")[1] if "|" in content else None
                        if expiry_str:
                            expiry = datetime.fromisoformat(expiry_str)
                            if now > expiry:
                                lock_file.unlink()
                                logger.debug(f"[FILE_LOCK] Cleaned expired lock: {lock_file.name}")
                except Exception as e:
                    logger.warning(f"[FILE_LOCK] Error cleaning lock {lock_file.name}: {e}")
        except Exception as e:
            logger.warning(f"[FILE_LOCK] Cleanup failed: {e}")

    def acquire(self, lock_key: str = "orchestrator-run-lock", timeout_seconds: int = 5) -> bool:
        """Acquire file-based lock.

        Args:
            lock_key: The lock identifier
            timeout_seconds: How long to retry acquiring lock

        Returns: True if lock acquired, False if another instance holds it
        """
        lock_file = self.lock_dir / f"{lock_key}.lock"
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
                        if datetime.utcnow() < expiry:
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

            # Try to acquire lock
            try:
                now = datetime.utcnow()
                expiry = now + timedelta(seconds=self.lock_duration_seconds)
                lock_content = f"local-dev|{expiry.isoformat()}"

                # Write lock file atomically
                with open(lock_file, "w", encoding="utf-8") as f:
                    f.write(lock_content)

                self.current_lock_file = lock_file
                logger.info(f"[FILE_LOCK] Lock acquired: {lock_file.name}")
                return True

            except Exception as e:
                logger.error(f"[FILE_LOCK] Failed to acquire lock: {e}")
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
) -> "FileLockManager | DynamoDBLockManager":
    """Factory function that returns appropriate lock manager based on LOCAL_MODE.

    Returns:
        FileLockManager in LOCAL_MODE, DynamoDBLockManager otherwise
    """
    if os.getenv("LOCAL_MODE", "").lower() == "true":
        logger.info("[LOCK_FACTORY] LOCAL_MODE detected - using file-based locks")
        return FileLockManager(
            table_name=table_name,
            lock_duration_seconds=lock_duration_seconds,
            enable_auto_cleanup=enable_auto_cleanup,
        )
    else:
        logger.info("[LOCK_FACTORY] Using DynamoDB locks")
        from utils.db.dynamo_lock import DynamoDBLockManager

        return DynamoDBLockManager(
            table_name=table_name,
            lock_duration_seconds=lock_duration_seconds,
            enable_auto_cleanup=enable_auto_cleanup,
        )
