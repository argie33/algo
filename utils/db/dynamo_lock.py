#!/usr/bin/env python3
"""DynamoDB-based distributed lock manager.

Replaces filesystem locks (Issue #8) with DynamoDB conditional writes
for correct Fargate/ECS distributed locking.
"""

import os
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional

try:
    import boto3
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)

class DynamoDBLockManager:
    """Distributed lock manager using DynamoDB conditional writes."""

    def __init__(
        self, table_name: Optional[str] = None, lock_duration_seconds: int = 600
    ):
        """Initialize lock manager.

        Args:
            table_name: DynamoDB table name (default: from ORCHESTRATOR_LOCK_TABLE env)
            lock_duration_seconds: Lock expiration time (default 10 minutes)
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
        self.lock_id = str(uuid.uuid4())
        self.acquired = False
        self.is_available = False  # Track if DynamoDB is actually usable

        if not boto3:
            logger.warning("boto3 not available — falling back to noop lock manager")
            self.dynamodb = None
            return

        try:
            self.dynamodb = boto3.resource("dynamodb")
            self.table = self.dynamodb.Table(self.table_name)
            self.is_available = True  # Successfully initialized
        except Exception as e:
            # DynamoDB unavailable due to permissions, network, or missing tables
            logger.warning(
                f"DynamoDB lock manager unavailable: {e}. Will skip distributed locking."
            )
            self.dynamodb = None
            self.is_available = False

    def acquire(
        self, lock_key: str = "orchestrator-run-lock", timeout_seconds: int = 5
    ) -> bool:
        """Acquire distributed lock using DynamoDB conditional write.

        Uses optimistic locking: if lock doesn't exist or is expired, we write our lock.
        If someone else holds a valid lock, we fail and return False.

        Args:
            lock_key: The lock identifier (default: 'orchestrator-run-lock')
            timeout_seconds: How long to retry acquiring lock

        Returns: True if lock acquired, False if another instance holds it
        """
        if not self.dynamodb:
            logger.warning(
                "[LOCK] DynamoDB unavailable — allowing execution without distributed lock (DEV MODE)"
            )
            self.acquired = False
            return True  # Allow execution to proceed even without DynamoDB

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                now = datetime.utcnow().isoformat()
                expiry = (
                    datetime.utcnow() + timedelta(seconds=self.lock_duration_seconds)
                ).isoformat()

                # Conditional write: only succeed if item doesn't exist OR is expired
                response = self.table.update_item(
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
                logger.info(f"[LOCK] Acquired lock {lock_key} (expires at {expiry})")
                return True

            except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                # Someone else holds a valid lock
                logger.warning(
                    f"[LOCK] Another instance holds {lock_key} — retrying..."
                )
                time.sleep(0.1)

            except Exception as e:
                # Check if this is a permission error (AccessDeniedException) vs. a lock contention issue
                if "AccessDeniedException" in str(type(e)) or "not authorized" in str(
                    e
                ):
                    logger.warning(
                        f"[LOCK] DynamoDB permission denied: {e} — marking as unavailable"
                    )
                    self.is_available = False
                    return False
                else:
                    logger.critical(
                        f"[LOCK] Error acquiring lock: {e} — refusing to proceed without lock."
                    )
                    return False

        logger.error(f"[LOCK] Failed to acquire {lock_key} after {timeout_seconds}s")
        return False

    def release(self, lock_key: str = "orchestrator-run-lock") -> bool:
        """Release the distributed lock.

        Only release if we still own it (lock_id matches).

        Args:
            lock_key: The lock identifier

        Returns: True if released, False on error
        """
        if not self.dynamodb or not self.acquired:
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

        except self.dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Someone else acquired the lock (shouldn't happen)
            logger.warning(
                f"[LOCK] Lock {lock_key} already released or acquired by another instance"
            )
            return False

        except Exception as e:
            logger.error(f"[LOCK] Error releasing lock: {e}")
            return False
