#!/usr/bin/env python3
"""DynamoDB Health Monitoring — Ensures halt flags and state management are working.

DynamoDB is critical for:
- orchestrator_halt flag (prevents Phase 5/6 during stale data)
- phase1_degraded_mode flag (indicates failsafe is running)
- orchestrator-run-lock (distributed lock for concurrent execution)
"""

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class DynamoDBHealthCheck:
    """Monitor DynamoDB availability and state consistency."""

    def __init__(self) -> None:
        self.table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
        self.region = os.getenv("AWS_REGION", "us-east-1")

    def check_dynamodb_connectivity(self) -> bool:
        """Test if DynamoDB is reachable.

        Returns:
            True if DynamoDB is responsive, False if unavailable
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            table = dynamodb.Table(self.table_name)

            # Attempt a simple read (head request doesn't consume capacity)
            table.get_item(Key={"key": "connectivity_check"}, ConsistentRead=False)

            logger.debug(f"[DynamoDB] Connectivity check OK ({self.table_name})")
            return True

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def get_halt_flag_status(self) -> dict[str, Any]:
        """Get current halt flag state from DynamoDB.

        Returns:
            {
                'halt_flag_active': bool,
                'set_time': datetime or None,
                'reason': str or None,
                'auto_clear_time': datetime or None,
                'available': bool,
                'last_checked': datetime
            }

        Raises:
            KeyError: If halt_flag field is missing or Item not found
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            table = dynamodb.Table(self.table_name)

            response = table.get_item(Key={"key": "orchestrator_halt"})
            item = response.get("Item")

            # EXPLICIT: Fail fast if Item is None (key doesn't exist)
            if item is None:
                raise KeyError(
                    "orchestrator_halt key not found in DynamoDB. "
                    "Halt flag state is not initialized. Cannot safely determine halt status."
                )

            # EXPLICIT: Check if halt_flag field exists before accessing
            if "halt_flag" not in item:
                raise KeyError(
                    "halt_flag missing from DynamoDB item 'orchestrator_halt'. "
                    "Item structure may have changed. Cannot safely determine halt status."
                )

            # EXPLICIT: Validate halt_flag is boolean (or None)
            halt_flag_value = item["halt_flag"]
            if halt_flag_value is None:
                logger.warning("[DynamoDB] halt_flag is None, treating as False")
                halt_active = False
            else:
                halt_active = halt_flag_value is True

            # EXPLICIT: Extract optional fields with explicit None handling
            set_time = item.get("set_at")
            reason = item.get("reason")
            ttl = item.get("TTL")

            # EXPLICIT: Only calculate auto_clear_time if TTL is present and numeric
            auto_clear_time = None
            if ttl is not None:
                try:
                    auto_clear_time = datetime.fromtimestamp(ttl)
                except (ValueError, TypeError, OSError) as e:
                    logger.warning(f"[DynamoDB] Failed to parse TTL timestamp {ttl}: {e}")

            return {
                "halt_flag_active": halt_active,
                "set_time": set_time,
                "reason": reason,
                "auto_clear_time": auto_clear_time,
                "available": True,
                "last_checked": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[DynamoDB] Failed to read halt flag: {e}")
            return {
                "halt_flag_active": None,
                "available": False,
                "error": str(e),
                "last_checked": datetime.now().isoformat(),
            }

    def get_phase1_degraded_mode_status(self) -> dict[str, Any]:
        """Get Phase 1 degraded mode status.

        Returns:
            {
                'degraded_mode_active': bool,
                'reason': str or None,
                'set_time': datetime or None,
                'available': bool
            }

        Note:
            If key not found, defaults to False (no degraded mode).
            If degraded field is missing/None, treats as False (EXPLICIT INTENT).
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            table = dynamodb.Table(self.table_name)

            response = table.get_item(Key={"key": "phase1_degraded_mode"})
            item = response.get("Item")

            # EXPLICIT: If key doesn't exist, return default (no degraded mode)
            if item is None:
                logger.debug("[DynamoDB] phase1_degraded_mode key not found, defaulting to degraded=False")
                return {
                    "degraded_mode_active": False,
                    "reason": None,
                    "set_time": None,
                    "available": True,
                }

            # EXPLICIT: Extract degraded field; if None, treat as False (not truthy)
            degraded_value = item.get("degraded")
            if degraded_value is None:
                logger.debug("[DynamoDB] degraded field is None, treating as False")
                degraded = False
            else:
                # EXPLICIT: Coerce to boolean (is True, not just truthy)
                degraded = degraded_value is True

            # EXPLICIT: Extract optional fields with explicit None handling
            reason = item.get("reason")
            set_time = item.get("set_at")

            return {
                "degraded_mode_active": degraded,
                "reason": reason,
                "set_time": set_time,
                "available": True,
            }

        except Exception as e:
            logger.error(f"[DynamoDB] Failed to read phase1_degraded_mode: {e}")
            return {
                "degraded_mode_active": None,
                "available": False,
                "error": str(e),
            }

    def check_lock_status(self) -> dict[str, Any]:
        """Check distributed lock status (orchestrator-run-lock).

        Returns:
            {
                'lock_active': bool,
                'owner_run_id': str or None,
                'acquired_at': datetime or None,
                'expires_at': datetime or None,
                'available': bool
            }

        Note:
            If key not found, returns lock_active=False.
            If lock_owner field missing, treats as not held (lock_active=False).
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb", region_name=self.region)
            table = dynamodb.Table(self.table_name)

            response = table.get_item(Key={"key": "orchestrator-run-lock"})
            item = response.get("Item")

            # EXPLICIT: If Item is None, lock is not held
            if item is None:
                logger.debug("[DynamoDB] orchestrator-run-lock key not found, lock is free")
                return {
                    "lock_active": False,
                    "owner_run_id": None,
                    "acquired_at": None,
                    "expires_at": None,
                    "available": True,
                }

            # EXPLICIT: Check if lock_owner field exists (indicates lock is held)
            lock_active = "lock_owner" in item and item["lock_owner"] is not None

            # EXPLICIT: Extract optional fields with explicit None handling
            owner = item.get("lock_owner")
            acquired_at = item.get("lock_acquired_at")
            ttl = item.get("TTL")

            # EXPLICIT: Only calculate expires_at if TTL is present and numeric
            expires_at = None
            if ttl is not None:
                try:
                    expires_at = datetime.fromtimestamp(ttl)
                except (ValueError, TypeError, OSError) as e:
                    logger.warning(f"[DynamoDB] Failed to parse lock TTL timestamp {ttl}: {e}")

            return {
                "lock_active": lock_active,
                "owner_run_id": owner,
                "acquired_at": acquired_at,
                "expires_at": expires_at,
                "available": True,
            }

        except Exception as e:
            logger.error(f"[DynamoDB] Failed to read lock status: {e}")
            return {
                "lock_active": None,
                "available": False,
                "error": str(e),
            }

    def log_health_status(self) -> None:
        """Log comprehensive DynamoDB health status."""
        connected = self.check_dynamodb_connectivity()

        if not connected:
            logger.critical("[DynamoDB] UNAVAILABLE - State management disabled!")
            return

        halt_status = self.get_halt_flag_status()
        degraded_status = self.get_phase1_degraded_mode_status()
        lock_status = self.check_lock_status()

        logger.info(
            "[DynamoDB-Health] "
            f"Halt={'ACTIVE' if halt_status.get('halt_flag_active') else 'clear'}, "
            f"Degraded={'YES' if degraded_status.get('degraded_mode_active') else 'NO'}, "
            f"Lock={'HELD' if lock_status.get('lock_active') else 'free'}"
        )
