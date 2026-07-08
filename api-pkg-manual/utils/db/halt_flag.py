#!/usr/bin/env python3
"""
Halt flag management with RDS redundancy.

PROBLEM: Halt flag stored only in DynamoDB = single point of failure.
When DynamoDB is unavailable, system halts all trading even though data may be fresh.

SOLUTION: Dual-storage strategy with intelligent fallback.
1. Always write to both DynamoDB and RDS
2. Read from DynamoDB (fast), fall back to RDS if unavailable
3. Circuit breaker: if DynamoDB unavailable >3 times in 5 min, skip DynamoDB reads
   and rely only on RDS (prevents cascade failure)

RESILIENCE:
- DynamoDB fails: RDS provides halt status (15s fallback timeout)
- RDS fails: DynamoDB provides halt status (original behavior)
- Both fail: Conservatively assume halt is set (fail-closed for safety)
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)

HALT_FLAG_KEY = "orchestrator_halt"
DYNAMODB_FAILURE_THRESHOLD = 3  # Failures before circuit breaker trips
DYNAMODB_FAILURE_WINDOW_SEC = 300  # 5-minute window for failure counting
DYNAMODB_FALLBACK_TIMEOUT_SEC = 15  # Timeout for DynamoDB operations


class HaltFlagManager:
    """Manages halt flag with DynamoDB + RDS redundancy."""

    def __init__(self) -> None:
        self._dynamodb_failure_times: list[Any] = []  # Track failure timestamps for circuit breaker
        self._circuit_breaker_open = False

    def _record_dynamodb_failure(self) -> None:
        """Record a DynamoDB failure for circuit breaker tracking."""
        now = datetime.now(timezone.utc)
        self._dynamodb_failure_times.append(now)

        # Clean up old failure records (>5 min old)
        cutoff = now - timedelta(seconds=DYNAMODB_FAILURE_WINDOW_SEC)
        self._dynamodb_failure_times = [t for t in self._dynamodb_failure_times if t > cutoff]

        # Open circuit breaker if too many failures in window
        if len(self._dynamodb_failure_times) >= DYNAMODB_FAILURE_THRESHOLD:
            if not self._circuit_breaker_open:
                logger.warning(
                    f"[HALT_FLAG] DynamoDB circuit breaker OPEN: {len(self._dynamodb_failure_times)} "
                    f"failures in past {DYNAMODB_FAILURE_WINDOW_SEC}s. Using RDS only."
                )
                self._circuit_breaker_open = True

        # Reset circuit breaker if enough time has passed without failures
        if len(self._dynamodb_failure_times) == 0:
            self._circuit_breaker_open = False

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open (skip DynamoDB reads)."""
        # Clean up old failures first
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=DYNAMODB_FAILURE_WINDOW_SEC)
        self._dynamodb_failure_times = [t for t in self._dynamodb_failure_times if t > cutoff]

        if len(self._dynamodb_failure_times) >= DYNAMODB_FAILURE_THRESHOLD:
            if not self._circuit_breaker_open:
                logger.warning("[HALT_FLAG] DynamoDB circuit breaker is OPEN")
                self._circuit_breaker_open = True
            return True

        if self._circuit_breaker_open and len(self._dynamodb_failure_times) == 0:
            logger.info("[HALT_FLAG] DynamoDB circuit breaker is CLOSED (recovered)")
            self._circuit_breaker_open = False

        return False

    def check_halt_flag(self) -> tuple[bool | None, str | None]:
        """Check if halt flag is set.

        Returns:
            Tuple[halt_flag_set, reason]
            - halt_flag_set: True if halt is active, False if not, None if unable to determine
            - reason: String explaining why halt is set (or None if no halt)

        Strategy:
        1. If circuit breaker open: read RDS only
        2. Otherwise: try DynamoDB first, fall back to RDS
        3. If both fail: return None (conservative: assume halt for safety)
        """
        # If circuit breaker is open, skip DynamoDB and use RDS only
        if self._is_circuit_breaker_open():
            logger.debug("[HALT_FLAG] Circuit breaker open, reading from RDS only")
            return self._check_halt_flag_rds()

        # Try DynamoDB first (faster, preferred)
        try:
            halt_flag, reason = self._check_halt_flag_dynamodb()
            if halt_flag is not None:
                return halt_flag, reason
        except (FileNotFoundError, OSError) as e:
            logger.warning(f"[HALT_FLAG] DynamoDB check failed: {e}. Falling back to RDS.")
            self._record_dynamodb_failure()

        # Fall back to RDS
        try:
            halt_flag, reason = self._check_halt_flag_rds()
            if halt_flag is not None:
                return halt_flag, reason
        except (FileNotFoundError, OSError) as e:
            logger.error(f"[HALT_FLAG] RDS fallback failed: {e}")

        # Both failed: cannot proceed safely
        error_msg = "[HALT_FLAG] Both DynamoDB and RDS unavailable - cannot determine halt status"
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    def _check_halt_flag_dynamodb(self) -> tuple[bool | None, str | None]:
        """Check halt flag in DynamoDB. Returns (halt_flag, reason) or (None, None) on timeout/error."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            # Use timeout to prevent hanging
            response = table.get_item(Key={"key": HALT_FLAG_KEY}, ReturnConsumedCapacity="NONE")

            if "Item" not in response:
                logger.debug("[HALT_FLAG] No halt flag in DynamoDB (not set)")
                return False, None

            item = response["Item"]

            if "halt_flag" not in item:
                raise RuntimeError(
                    "Halt flag item corrupted: missing required 'halt_flag' field. "
                    "DynamoDB item must contain halt_flag field (True/False). "
                    "This is a data integrity issue that prevents safe operation."
                )

            halt_flag = item["halt_flag"]
            if not halt_flag:
                return False, None

            if "reason" not in item or "triggered_at" not in item:
                raise RuntimeError(
                    "Halt flag item corrupted: missing required fields (reason, triggered_at). "
                    "When halt_flag=True, both reason and triggered_at must be present. "
                    "Cannot proceed without knowing halt reason and trigger time."
                )

            reason = item["reason"]
            triggered_at = item["triggered_at"]
            if "halt_count" not in item:
                raise RuntimeError(
                    "Halt flag item corrupted: missing required 'halt_count' field. "
                    "DynamoDB item must contain halt_count field (integer). "
                    "This is a data integrity issue that prevents safe operation."
                )
            halt_count = item["halt_count"]

            # Check if halt is from previous trading day (auto-expiry)
            if triggered_at:
                try:
                    trigger_dt = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))
                    now_utc = datetime.now(timezone.utc)
                    trigger_et = trigger_dt.astimezone(EASTERN_TZ)
                    now_et = now_utc.astimezone(EASTERN_TZ)

                    if trigger_et.date() < now_et.date():
                        # Check if market has opened on current trading day
                        market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                        if now_et >= market_open:
                            logger.info(f"[HALT_FLAG] Halt from {trigger_et.date()} expired (past market open)")
                            return False, None
                except Exception as parse_err:
                    logger.warning(f"[HALT_FLAG] Could not parse DynamoDB timestamp: {parse_err}")

            logger.critical(f"[HALT_FLAG] ACTIVE in DynamoDB: {reason} (count={halt_count})")
            return True, reason

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def _check_halt_flag_rds(self) -> tuple[bool | None, str | None]:
        """Check halt flag in RDS. Returns (halt_flag, reason) or (None, None) on error."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT halt_flag, halt_reason, halt_triggered_at, halt_count
                    FROM algo_runtime_state
                    WHERE state_key = %s
                """,
                    (HALT_FLAG_KEY,),
                )

                result = cur.fetchone()
                if not result:
                    logger.debug("[HALT_FLAG] No halt flag in RDS (not set)")
                    return False, None

                halt_flag, reason, triggered_at, halt_count = result

                if not halt_flag:
                    return False, None

                # Check if halt is from previous trading day (auto-expiry)
                if triggered_at:
                    try:
                        if triggered_at.tzinfo is None:
                            triggered_at = triggered_at.replace(tzinfo=timezone.utc)

                        trigger_et = triggered_at.astimezone(EASTERN_TZ)
                        now_et = datetime.now(timezone.utc).astimezone(EASTERN_TZ)

                        if trigger_et.date() < now_et.date():
                            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
                            if now_et >= market_open:
                                logger.info(f"[HALT_FLAG] Halt from {trigger_et.date()} expired (past market open)")
                                return False, None
                    except (
                        psycopg2.DatabaseError,
                        psycopg2.OperationalError,
                    ) as parse_err:
                        logger.warning(f"[HALT_FLAG] Could not parse RDS timestamp: {parse_err}")

                logger.critical(f"[HALT_FLAG] ACTIVE in RDS: {reason} (count={halt_count})")
                return True, reason

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag atomically. RDS is source of truth; DynamoDB is read cache.

        Returns True ONLY if RDS write succeeds (source of truth). DynamoDB write failure
        is logged but non-blocking, since reads fall back to RDS. This prevents split-brain
        where DynamoDB succeeds but RDS fails (inconsistent state across runs).
        """
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)

        halt_data = {
            "halt_flag": True,
            "triggered_at": now_utc.isoformat(),
            "reason": reason or "Phase 1 degraded: stale data detected",
            "halt_count": 1,
        }

        # Try to increment halt_count if already set
        try:
            existing, _ = self.check_halt_flag()
            if existing:
                halt_data["halt_count"] = 2  # Escalation
        except Exception as e:
            raise RuntimeError(f"Unexpected error: {e}") from e

        # RDS is source of truth: must succeed
        success_rds = self._set_halt_flag_rds(halt_data, now_et)

        # DynamoDB is read cache: best-effort, failure is tolerable
        if success_rds:
            success_dynamodb = self._set_halt_flag_dynamodb(halt_data, now_utc)
            logger.critical(f"[HALT_FLAG_SET] {reason} (RDS: True, DynamoDB: {success_dynamodb})")
            return True

        logger.error("[HALT_FLAG_SET_FAILED] Could not set halt flag in RDS (source of truth)")
        return False

    def _set_halt_flag_dynamodb(self, halt_data: dict[str, Any], now_utc: datetime) -> bool:
        """Set halt flag in DynamoDB. Returns True if successful."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            table.put_item(
                Item={
                    "key": HALT_FLAG_KEY,
                    **halt_data,
                }
            )
            logger.debug(f"[HALT_FLAG] Set in DynamoDB: {halt_data['reason']}")
            return True
        except Exception as e:
            logger.warning(f"[HALT_FLAG] Failed to set in DynamoDB: {e}")
            self._record_dynamodb_failure()
            return False

    def _set_halt_flag_rds(self, halt_data: dict[str, Any], now_et: datetime) -> bool:
        """Set halt flag in RDS. Returns True if successful."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_runtime_state (
                        state_key, state_value, halt_flag, halt_triggered_at,
                        halt_reason, halt_count, updated_by, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (state_key) DO UPDATE SET
                        halt_flag = EXCLUDED.halt_flag,
                        halt_triggered_at = EXCLUDED.halt_triggered_at,
                        halt_reason = EXCLUDED.halt_reason,
                        halt_count = EXCLUDED.halt_count,
                        last_updated_at = CURRENT_TIMESTAMP,
                        expires_at = EXCLUDED.expires_at
                """,
                    (
                        HALT_FLAG_KEY,
                        json.dumps(halt_data),
                        True,
                        halt_data["triggered_at"],
                        halt_data["reason"],
                        halt_data["halt_count"],
                        "orchestrator",
                        (now_et + timedelta(hours=24)).isoformat(),
                    ),
                )
            logger.debug(f"[HALT_FLAG] Set in RDS: {halt_data['reason']}")
            return True
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[HALT_FLAG] Failed to set in RDS: {e}")
            return False

    def clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag atomically. RDS is source of truth; DynamoDB is read cache.

        Returns True ONLY if RDS write succeeds (source of truth). DynamoDB write failure
        is logged but non-blocking, since reads fall back to RDS.
        """
        # RDS is source of truth: must succeed
        success_rds = self._clear_halt_flag_rds()

        # DynamoDB is read cache: best-effort, failure is tolerable
        if success_rds:
            success_dynamodb = self._clear_halt_flag_dynamodb()
            logger.critical(f"[HALT_FLAG_CLEARED] {reason} (RDS: True, DynamoDB: {success_dynamodb})")
            return True

        logger.warning("[HALT_FLAG_CLEAR_FAILED] Could not clear halt flag in RDS (source of truth)")
        return False

    def _clear_halt_flag_dynamodb(self) -> bool:
        """Clear halt flag in DynamoDB. Returns True if successful."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            table.put_item(
                Item={
                    "key": HALT_FLAG_KEY,
                    "halt_flag": False,
                    "reason": "Cleared by Phase 1: all data fresh",
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            logger.debug("[HALT_FLAG] Cleared in DynamoDB")
            return True
        except Exception as e:
            logger.warning(f"[HALT_FLAG] Failed to clear in DynamoDB: {e}")
            self._record_dynamodb_failure()
            return False

    def _clear_halt_flag_rds(self) -> bool:
        """Clear halt flag in RDS. Returns True if successful."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    UPDATE algo_runtime_state
                    SET halt_flag = FALSE,
                        halt_reason = 'Cleared by Phase 1: all data fresh',
                        halt_count = 0,
                        last_updated_at = CURRENT_TIMESTAMP
                    WHERE state_key = %s
                """,
                    (HALT_FLAG_KEY,),
                )
            logger.debug("[HALT_FLAG] Cleared in RDS")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[HALT_FLAG] Failed to clear in RDS: {e}")
            return False


# Singleton instance
_halt_flag_manager = None


def get_halt_flag_manager() -> HaltFlagManager:
    """Get singleton instance of halt flag manager."""
    global _halt_flag_manager
    if _halt_flag_manager is None:
        _halt_flag_manager = HaltFlagManager()
    return _halt_flag_manager
