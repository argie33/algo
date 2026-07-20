"""RDS-based distributed lock manager fallback for when DynamoDB is unavailable.

Used when AWS credentials are missing or DynamoDB is unreachable.
Provides the same interface as DynamoDBLockManager for compatibility.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class RDSLockManager:
    """RDS-based distributed lock manager (fallback when DynamoDB unavailable).

    Uses PostgreSQL for locking with automatic expiration. Less performant than
    DynamoDB but works without AWS credentials and supports local development.
    """

    def __init__(
        self, table_name: str | None = None, lock_duration_seconds: int = 600, enable_auto_cleanup: bool = True
    ):
        """Initialize lock manager.

        Args:
            table_name: Lock table name (ignored - always uses loader_execution_locks)
            lock_duration_seconds: Lock expiration time (default 10 minutes)
            enable_auto_cleanup: Automatically clean expired locks on startup
        """
        self.lock_duration_seconds = lock_duration_seconds
        self.enable_auto_cleanup = enable_auto_cleanup
        self.lock_id = str(uuid.uuid4())
        self.acquired = False
        self.is_available = True
        self.lock_key = "orchestrator-run-lock"

        try:
            # Test RDS connectivity
            with DatabaseContext("read") as cur:
                cur.execute("SELECT 1")
            logger.info("[RDS_LOCK] RDS lock manager initialized")
        except Exception as e:
            logger.error(f"[RDS_LOCK] RDS lock manager initialization failed: {e}")
            self.is_available = False

    def acquire(self, lock_key: str = "orchestrator-run-lock", timeout_seconds: int = 5) -> bool:
        """Acquire distributed lock using RDS.

        Uses an INSERT or UPDATE on the lock table with expiration timestamps.

        Args:
            lock_key: The lock identifier
            timeout_seconds: How long to retry acquiring lock

        Returns: True if lock acquired, False if another instance holds it
        """
        start_time = time.time()
        attempt = 0
        self.lock_key = lock_key

        while time.time() - start_time < timeout_seconds:
            attempt += 1
            try:
                now_utc = datetime.now(timezone.utc)
                expires_at = now_utc + timedelta(seconds=self.lock_duration_seconds)

                with DatabaseContext("write") as cur:
                    # Try to acquire lock atomically
                    # Use INSERT ... ON CONFLICT to ensure atomicity
                    # Lock succeeds if no existing lock OR existing lock is expired
                    cur.execute(
                        """
                        INSERT INTO loader_execution_locks (loader_name, locked_by, locked_at, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (loader_name) DO UPDATE SET
                            locked_by = EXCLUDED.locked_by,
                            locked_at = EXCLUDED.locked_at,
                            expires_at = EXCLUDED.expires_at
                        WHERE loader_execution_locks.expires_at < NOW()
                        """,
                        (lock_key, self.lock_id, now_utc, expires_at),
                    )

                    # Verify we got the lock by checking if our lock_id matches
                    cur.execute(
                        "SELECT locked_by FROM loader_execution_locks WHERE loader_name = %s",
                        (lock_key,),
                    )
                    result = cur.fetchone()
                    if result and result[0] == self.lock_id:
                        self.acquired = True
                        logger.info(f"[RDS_LOCK] Acquired lock {lock_key} on attempt {attempt}")
                        return True
                    else:
                        # Someone else holds the lock
                        logger.debug(f"[RDS_LOCK] Another instance holds {lock_key} - retrying...")

            except Exception as e:
                logger.debug(f"[RDS_LOCK] Error acquiring lock on attempt {attempt}: {e}")
                if "permission denied" in str(e).lower() or "not authorized" in str(e).lower():
                    self.is_available = False
                    return False

            # Exponential backoff: 50ms, 100ms, 200ms up to 500ms
            backoff = min(0.05 * (2 ** (attempt - 1)), 0.5)
            time.sleep(backoff)

        logger.warning(
            f"[RDS_LOCK] Failed to acquire {lock_key} after {timeout_seconds}s ({attempt} attempts). "
            f"Lock will expire in {self.lock_duration_seconds}s."
        )
        return False

    def release(self, lock_key: str = "orchestrator-run-lock") -> bool:
        """Release the distributed lock.

        Only release if we still own it (lock_id matches).

        Args:
            lock_key: The lock identifier

        Returns: True if released, False on error
        """
        if not self.acquired:
            return True

        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    DELETE FROM loader_execution_locks
                    WHERE loader_name = %s AND locked_by = %s
                    """,
                    (lock_key, self.lock_id),
                )
                self.acquired = False
                logger.info(f"[RDS_LOCK] Released lock {lock_key}")
                return True

        except Exception as e:
            logger.error(f"[RDS_LOCK] Error releasing lock {lock_key}: {e}")
            self.acquired = False
            raise RuntimeError(f"Operation failed: {e}") from e

    def cleanup_expired_locks(self, lock_key: str | None = None, max_age_seconds: int = 1800) -> int:
        """Clean up expired locks from RDS.

        Args:
            lock_key: Specific lock to clean (optional)
            max_age_seconds: Locks older than this are considered expired

        Returns:
            Number of locks cleaned up
        """
        if not self.enable_auto_cleanup:
            return 0

        try:
            cleaned = 0
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)

            with DatabaseContext("write") as cur:
                if lock_key:
                    # Clean specific lock
                    cur.execute(
                        "DELETE FROM loader_execution_locks WHERE loader_name = %s AND expires_at < %s",
                        (lock_key, cutoff_time),
                    )
                    cleaned = cur.rowcount
                else:
                    # Clean all expired locks
                    cur.execute("DELETE FROM loader_execution_locks WHERE expires_at < %s", (cutoff_time,))
                    cleaned = cur.rowcount

            if cleaned > 0:
                logger.info(f"[RDS_LOCK_CLEANUP] Cleaned {cleaned} expired locks")
            return cleaned

        except Exception as e:
            logger.error(f"[RDS_LOCK_CLEANUP] Failed to clean locks: {e}")
            return 0

    def get_lock_status(self, lock_key: str) -> dict[str, str | bool]:
        """Get current status of a lock (diagnostic tool).

        Args:
            lock_key: The lock identifier

        Returns:
            Dictionary with lock status, holder, and expiry time
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT locked_by, locked_at, expires_at
                    FROM loader_execution_locks
                    WHERE loader_name = %s
                    """,
                    (lock_key,),
                )
                result = cur.fetchone()

                if not result:
                    return {"status": "free"}

                locked_by, locked_at, expires_at = result
                is_expired = expires_at < datetime.now(timezone.utc) if expires_at else False

                return {
                    "status": "expired" if is_expired else "held",
                    "lock_holder_id": locked_by,
                    "acquired_at": locked_at.isoformat() if locked_at else "unknown",
                    "expires_at": expires_at.isoformat() if expires_at else "unknown",
                    "is_expired": is_expired,
                }

        except Exception as e:
            return {"status": "error", "error": str(e)}
