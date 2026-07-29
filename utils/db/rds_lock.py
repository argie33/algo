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
        self.acquired_lock_id = None  # Track the actual lock_id stored in database

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

        # CRITICAL: Clean up any expired locks for this key BEFORE trying to acquire
        # This prevents stale locks from crashed processes blocking acquisition indefinitely
        try:
            self.cleanup_expired_locks(lock_key=lock_key, max_age_seconds=self.lock_duration_seconds)
        except Exception as e:
            logger.warning(f"[RDS_LOCK] Failed to cleanup stale locks for {lock_key}: {e}. Proceeding anyway.")

        while time.time() - start_time < timeout_seconds:
            attempt += 1
            try:
                now_utc = datetime.now(timezone.utc)
                expires_at = now_utc + timedelta(seconds=self.lock_duration_seconds)

                with DatabaseContext("write") as cur:
                    # Try to acquire lock atomically
                    # First, delete any expired locks for this key
                    # CRITICAL: expires_at is `timestamp with time zone`, stored in server's local timezone (EDT).
                    # When comparing against NOW(), must ensure both sides are in same timezone representation.
                    # NOW() returns `timestamp with time zone` in server local time (EDT).
                    # expires_at is already `timestamp with time zone` (stored in EDT), so compare directly:
                    # If expires_at (EDT) < NOW() (EDT), then lock is expired. This works because both are
                    # `timestamp with time zone` and PostgreSQL compares them correctly.
                    cur.execute(
                        "DELETE FROM loader_execution_locks WHERE loader_name = %s AND expires_at < NOW()",
                        (lock_key,),
                    )

                    # Try to insert our lock. ON CONFLICT DO NOTHING (not a bare INSERT wrapped
                    # in try/except) - contention on this loader_name PK is the expected,
                    # routine outcome of this retry loop, not an error. A bare INSERT relies on
                    # catching the resulting UniqueViolation, but DatabaseContext's cursor wrapper
                    # unconditionally logs any DatabaseError at ERROR level (with full traceback)
                    # before this code gets a chance to catch and downgrade it to DEBUG -
                    # confirmed live 2026-07-27: 13 retry attempts against an already-held lock
                    # produced 13 ERROR-level tracebacks in the orchestrator log for a completely
                    # normal contention case. ON CONFLICT DO NOTHING never raises, so it stays
                    # atomic (no TOCTOU race vs a plain check-then-insert) without the log noise.
                    cur.execute(
                        """
                        INSERT INTO loader_execution_locks (loader_name, locked_by, locked_at, expires_at)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (loader_name) DO NOTHING
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
                        self.acquired_lock_id = result[0]  # Save actual lock_id for later verification
                        logger.info(f"[RDS_LOCK] Acquired lock {lock_key} on attempt {attempt}")
                        return True

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

    def release(self, lock_key: str | None = None) -> bool:
        """Release the distributed lock.

        Only release if we still own it (lock_id matches).

        Args:
            lock_key: The lock identifier. CRITICAL FIX: this used to default to the
                hardcoded string "orchestrator-run-lock" instead of self.lock_key (the key
                actually recorded by acquire()). Any caller that acquires a non-default lock
                (every loader lock - see utils/optimal_loader.py's
                `lock_manager.acquire(lock_key=self.table_name, ...)`) and then calls
                `.release()` with no argument would silently attempt to delete the WRONG row
                ("orchestrator-run-lock" instead of the loader's own lock), leaving the real
                lock held until its 600s TTL naturally expires - reproduced live 2026-07-27
                via a standalone acquire/release script. No current call site actually hits
                this (all pass lock_key explicitly to both acquire and release), but it's a
                live footgun in a safety-critical shared utility. Default to the key this
                instance actually acquired instead of an unrelated hardcoded string.

        Returns: True if released, False on error
        """
        if not self.acquired:
            return True

        if lock_key is None:
            lock_key = self.lock_key

        try:
            with DatabaseContext("write") as cur:
                # DEBUG: Check what locks exist before attempting delete
                cur.execute(
                    "SELECT loader_name, locked_by, expires_at FROM loader_execution_locks WHERE loader_name = %s",
                    (lock_key,),
                )
                existing = cur.fetchall()

                # Use acquired_lock_id if available (the actual ID stored when we acquired)
                # Otherwise fall back to self.lock_id (for backward compatibility with manually created locks)
                delete_lock_id = self.acquired_lock_id if self.acquired_lock_id else self.lock_id

                cur.execute(
                    """
                    DELETE FROM loader_execution_locks
                    WHERE loader_name = %s AND locked_by = %s
                    """,
                    (lock_key, delete_lock_id),
                )
                deleted = cur.rowcount
                self.acquired = False
                if deleted == 0:
                    # Log what was in the database for debugging
                    if existing:
                        existing_lock_id = existing[0][1] if existing and len(existing[0]) > 1 else "unknown"
                        logger.error(
                            f"[RDS_LOCK] Release for {lock_key} affected 0 rows. "
                            f"Expected locked_by={delete_lock_id}, but database has locked_by={existing_lock_id}. "
                            f"This indicates: (1) we acquired a different process's lock, or (2) another instance "
                            f"overwrote our lock, or (3) the lock was manually deleted. Lock will remain until TTL expires."
                        )
                    else:
                        logger.error(
                            f"[RDS_LOCK] Release for {lock_key} found no locks (affected 0 rows). "
                            f"Lock may have already expired or been deleted by another process."
                        )
                    # CRITICAL: a 0-row delete means this instance did NOT actually free the
                    # lock it thinks it holds. Surface this loudly instead of logging a false "Released".
                    return False
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
                    cleaned = int(cur.rowcount)
                else:
                    # Clean all expired locks
                    cur.execute("DELETE FROM loader_execution_locks WHERE expires_at < %s", (cutoff_time,))
                    cleaned = int(cur.rowcount)

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
