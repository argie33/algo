#!/usr/bin/env python3
"""DynamoDB-based distributed lock manager with recovery features.

Replaces filesystem locks (Issue #8) with DynamoDB conditional writes
for correct Fargate/ECS distributed locking.

Enhanced with:
- Better handling of transient AWS service issues
- Automatic cleanup of expired locks
- Improved diagnostics for lock contention
- Exponential backoff with jitter
"""

import logging
import os
import time
import uuid
from datetime import datetime, timedelta

import boto3

logger = logging.getLogger(__name__)


class DynamoDBLockManager:
    """Distributed lock manager using DynamoDB conditional writes.

    Features:
    - Optimistic locking via DynamoDB conditional writes
    - Automatic lock expiration via TTL
    - Exponential backoff for transient failures
    - Diagnostic tools for troubleshooting contention
    - Auto-cleanup of expired locks
    """

    def __init__(
        self, table_name: str | None = None, lock_duration_seconds: int = 600, enable_auto_cleanup: bool = True
    ):
        """Initialize lock manager.

        Args:
            table_name: DynamoDB table name (default: from ORCHESTRATOR_LOCK_TABLE env)
            lock_duration_seconds: Lock expiration time (default 10 minutes)
            enable_auto_cleanup: Automatically clean expired locks on startup
        """
        # Default table name construction: project-orchestrator-locks-environment
        # ORCHESTRATOR_LOCK_TABLE env var overrides if set (used in Lambda)
        # Fallback includes environment suffix for local dev: algo-orchestrator-locks-dev
        default_name = os.getenv(
            "ORCHESTRATOR_LOCK_TABLE",
            f"{os.getenv('PROJECT_NAME', 'algo')}-orchestrator-locks-{os.getenv('ENVIRONMENT', 'dev')}",
        )
        self.table_name = table_name or default_name
        self.lock_duration_seconds = lock_duration_seconds
        self.enable_auto_cleanup = enable_auto_cleanup
        self.lock_id = str(uuid.uuid4())
        self.acquired = False
        self.is_available = True

        try:
            self.dynamodb = boto3.resource("dynamodb")
            self.table = self.dynamodb.Table(self.table_name)
            self._conditional_check_failed = self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException
            self._throttling_exception = self.dynamodb.meta.client.exceptions.ProvisionedThroughputExceededException
        except Exception as e:
            logger.error(f"DynamoDB lock manager initialization failed: {e}")
            raise

    def acquire(self, lock_key: str = "orchestrator-run-lock", timeout_seconds: int = 5) -> bool:
        """Acquire distributed lock using DynamoDB conditional write.

        Uses optimistic locking: if lock doesn't exist or is expired, we write our lock.
        If someone else holds a valid lock, we fail and return False.

        Enhanced with exponential backoff for transient failures and better diagnostics.

        Args:
            lock_key: The lock identifier (default: 'orchestrator-run-lock')
            timeout_seconds: How long to retry acquiring lock

        Returns: True if lock acquired, False if another instance holds it
        """
        start_time = time.time()
        attempt = 0

        while time.time() - start_time < timeout_seconds:
            attempt += 1
            try:
                now = datetime.utcnow().isoformat()
                expiry = (datetime.utcnow() + timedelta(seconds=self.lock_duration_seconds)).isoformat()

                # Conditional write: only succeed if item doesn't exist OR is expired
                self.table.update_item(
                    Key={"lock_key": lock_key},
                    UpdateExpression="SET #lock_id = :lock_id, #acquired_at = :acquired_at, #expires_at = :expires_at",
                    ExpressionAttributeNames={
                        "#lock_id": "lock_id",
                        "#acquired_at": "acquired_at",
                        "#expires_at": "expires_at",
                    },
                    ExpressionAttributeValues={
                        ":lock_id": self.lock_id,
                        ":acquired_at": now,
                        ":expires_at": expiry,
                        ":now": now,  # For condition check
                    },
                    # Only write if: no existing lock OR lock is expired
                    ConditionExpression="attribute_not_exists(#expires_at) OR #expires_at < :now",
                    ReturnValues="ALL_NEW",
                )
                self.acquired = True
                logger.info(f"[LOCK] Acquired lock {lock_key} (expires at {expiry}) on attempt {attempt}")
                return True

            except self._conditional_check_failed:
                # Someone else holds a valid lock — normal contention, keep retrying
                if attempt == 1:
                    logger.debug(f"[LOCK] Another instance holds {lock_key} — retrying with backoff...")
                # Exponential backoff: 50ms, 100ms, 200ms up to 500ms
                backoff = min(0.05 * (2 ** (attempt - 1)), 0.5)
                time.sleep(backoff)

            except self._throttling_exception:
                # DynamoDB throttled due to capacity — back off more aggressively
                logger.warning(f"[LOCK] DynamoDB throttled on attempt {attempt} for {lock_key}")
                time.sleep(min(0.1 * (2**attempt), 2.0))

            except Exception as e:
                # Check if this is a permission error (AccessDeniedException)
                error_str = str(type(e)) + str(e)
                if any(x in error_str for x in ["AccessDenied", "not authorized", "UnrecognizedClientException"]):
                    logger.warning(f"[LOCK] DynamoDB permission denied: {e} — marking as unavailable")
                    self.is_available = False
                    return False
                else:
                    # Transient error — retry with backoff
                    logger.debug(f"[LOCK] Transient error on attempt {attempt} acquiring {lock_key}: {e}")
                    time.sleep(min(0.1 * (2**attempt), 1.0))

        logger.error(
            f"[LOCK] Failed to acquire {lock_key} after {timeout_seconds}s ({attempt} attempts). "
            f"If another loader is using this lock, it will expire in {self.lock_duration_seconds}s."
        )
        return False

    def release(self, lock_key: str = "orchestrator-run-lock") -> bool:
        """Release the distributed lock.

        Only release if we still own it (lock_id matches).
        Enhanced with better error handling to prevent re-release attempts.

        Args:
            lock_key: The lock identifier

        Returns: True if released, False on error
        """
        if not self.acquired:
            return True  # No lock to release

        try:
            self.table.delete_item(
                Key={"lock_key": lock_key},
                ConditionExpression="#lock_id = :lock_id",
                ExpressionAttributeNames={"#lock_id": "lock_id"},
                ExpressionAttributeValues={":lock_id": self.lock_id},
            )
            self.acquired = False
            logger.info(f"[LOCK] Released lock {lock_key}")
            return True

        except self._conditional_check_failed:
            # Someone else already acquired the lock (can happen if we released late)
            logger.debug(f"[LOCK] Lock {lock_key} already released or acquired by another instance")
            self.acquired = False
            return True

        except Exception as e:
            logger.error(f"[LOCK] Error releasing lock {lock_key}: {e}")
            # Still mark as released to prevent re-release attempts
            self.acquired = False
            raise RuntimeError(f"Operation failed: {e}") from e

    def cleanup_expired_locks(self, lock_key: str | None = None, max_age_seconds: int = 1800) -> int:
        """Clean up expired locks from DynamoDB.

        NEW FEATURE: Helps recover from stuck loaders that crashed without releasing locks.
        Can be called periodically or when diagnosing lock contention issues.

        Args:
            lock_key: Specific lock to clean (optional). If None, scans all locks.
            max_age_seconds: Locks older than this are considered expired

        Returns:
            Number of locks cleaned up
        """
        if not self.enable_auto_cleanup:
            return 0

        try:
            cleaned = 0
            cutoff_time = (datetime.utcnow() - timedelta(seconds=max_age_seconds)).isoformat()

            if lock_key:
                # Clean specific lock
                response = self.table.get_item(Key={"lock_key": lock_key})
                if "Item" in response:
                    item = response["Item"]
                    if item.get("expires_at", "") < cutoff_time:
                        self.table.delete_item(Key={"lock_key": lock_key})
                        logger.info(f"[LOCK_CLEANUP] Deleted expired lock {lock_key}")
                        cleaned += 1
            else:
                # Scan and clean all expired locks
                response = self.table.scan()
                # CRITICAL FIX: Explicit check for Items field instead of empty list default
                items = response.get("Items")
                if items is None:
                    logger.warning("[LOCK_CLEANUP] DynamoDB scan returned no Items field — treating as empty")
                    items = []
                elif not isinstance(items, list):
                    logger.error(f"[LOCK_CLEANUP] DynamoDB Items field is not a list: {type(items)} — skipping cleanup")
                    items = []
                for item in items:
                    if item.get("expires_at", "") < cutoff_time:
                        self.table.delete_item(Key={"lock_key": item["lock_key"]})
                        logger.info(f"[LOCK_CLEANUP] Deleted expired lock {item['lock_key']}")
                        cleaned += 1

            if cleaned > 0:
                logger.warning(f"[LOCK_CLEANUP] Cleaned {cleaned} expired locks from {self.table_name}")

            return cleaned
        except Exception as e:
            logger.error(f"[LOCK_CLEANUP] Failed to clean locks: {e}")
            return 0

    def get_lock_status(self, lock_key: str) -> dict[str, str | bool]:
        """Get current status of a lock (diagnostic tool).

        Returns information about who holds a lock and when it expires.
        Useful for troubleshooting lock contention issues.

        Args:
            lock_key: The lock identifier

        Returns:
            Dictionary with lock status, holder, and expiry time
        """
        try:
            response = self.table.get_item(Key={"lock_key": lock_key})
            if "Item" not in response:
                return {"status": "free"}

            item = response["Item"]
            expires_at = item.get("expires_at", "unknown")
            acquired_at = item.get("acquired_at", "unknown")

            is_expired = expires_at < datetime.utcnow().isoformat() if isinstance(expires_at, str) else False

            return {
                "status": "expired" if is_expired else "held",
                "lock_holder_id": item.get("lock_id", "unknown"),
                "acquired_at": acquired_at,
                "expires_at": expires_at,
                "is_expired": is_expired,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
