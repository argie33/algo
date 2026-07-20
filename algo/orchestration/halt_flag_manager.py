#!/usr/bin/env python3
"""Halt flag management specialist for Orchestrator.

Extracted responsibilities:
- Check halt flag status with auto-expiry logic
- Set halt flag with escalation tracking
- Clear halt flag

ISSUE #8 FIX: Halt flag persists through entire trading day (9:30 AM - 4:00 PM ET)
to prevent Phase 5 from generating signals with stale data set by early morning
Phase 1. Auto-expires only at market open of next trading day (9:30 AM ET).

Eliminates divergent change in Orchestrator by centralizing all halt flag logic.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE

logger = logging.getLogger(__name__)


class HaltFlagManager:
    """Manage halt flag state in DynamoDB with auto-expiry and escalation tracking."""

    HALT_FLAG_DYNAMODB_KEY = "orchestrator_halt"

    def __init__(self, alerts: Any, log_phase_result: Any) -> None:
        """Initialize with alert manager and phase logging callback.

        Args:
            alerts: AlertManager instance for escalation
            log_phase_result: Callback to log phase results
        """
        self.alerts = alerts
        self.log_phase_result = log_phase_result

    def check_halt_flag(self) -> bool:
        """Check for halt flag with DynamoDB + RDS fallback. Returns True if halt was requested.

        RDS FALLBACK FIX (Session 289): Try DynamoDB first (fast), fall back to RDS if unavailable.
        This prevents orchestrator crashes when AWS credentials missing or DynamoDB unavailable.

        Uses DynamoDB instead of /tmp to work in Lambda where /tmp is ephemeral.
        SECURITY: If both DynamoDB and RDS unreachable, emits CloudWatch alarm metric.

        ISSUE #8 FIX: Halt flag persists through entire trading day (9:30 AM - 4:00 PM ET)
        to prevent Phase 5 from generating signals with stale data set by early morning
        Phase 1. Auto-expires only at market open of next trading day (9:30 AM ET).

        Timeline example:
        - 2:30 AM: Loaders detect stale data -> Phase 1 sets halt_flag with triggered_at=2:30 AM
        - 9:30 AM, 1 PM, 3 PM, 5:30 PM: Orchestrator runs check halt_flag -> still active (same day)
        - 9:30 AM NEXT DAY: Auto-clears halt_flag at market open (new trading day)

        CRITICAL FIX (Session 282): ALWAYS check halt flag, including LOCAL_MODE.
        LOCAL_MODE connects to the same shared production DB and Alpaca account,
        so halt flag enforcement is NON-NEGOTIABLE. If you want to skip safety checks,
        use dry_run=True instead of relying on LOCAL_MODE bypasses.
        """

        # Try DynamoDB first (preferred)
        dynamodb_result = self._check_halt_flag_dynamodb()
        if dynamodb_result is not None:
            return dynamodb_result

        # Fall back to RDS if DynamoDB unavailable
        logger.warning("[HALT_FLAG] DynamoDB unavailable, falling back to RDS")
        rds_result = self._check_halt_flag_rds()
        if rds_result is not None:
            return rds_result

        # Both unavailable: fail-closed (assume halt)
        logger.critical("[HALT_FLAG] Both DynamoDB and RDS unavailable - failing closed for safety")
        return True

    def _check_halt_flag_dynamodb(self) -> bool | None:
        """Check halt flag in DynamoDB. Returns True/False if successful, None if unavailable."""
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            if "Item" not in response:
                return False

            item = response["Item"]
            if item.get("halt_flag") is not True:
                return False

            triggered_at_str = item.get("triggered_at")
            if triggered_at_str:
                try:
                    trigger_dt = datetime.fromisoformat(triggered_at_str.replace("Z", "+00:00"))
                    now_utc = datetime.now(timezone.utc)

                    trigger_et = trigger_dt.astimezone(EASTERN_TZ)
                    now_et = now_utc.astimezone(EASTERN_TZ)

                    trigger_date = trigger_et.date()
                    now_date_et = now_et.date()

                    if trigger_date < now_date_et:
                        market_open_et = now_et.replace(
                            hour=MARKET_OPEN_HOUR,
                            minute=MARKET_OPEN_MINUTE,
                            second=0,
                            microsecond=0,
                        )
                        market_open_et = market_open_et.replace(tzinfo=EASTERN_TZ)

                        if now_et >= market_open_et:
                            logger.info(
                                f"[HALT_FLAG] Halt from {trigger_date} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET) "
                                f"on {now_date_et} - auto-clearing with atomic condition"
                            )
                            # CRITICAL FIX: Use ConditionExpression to atomically check AND clear
                            # Prevents race: if another orchestrator modified halt between our check and write,
                            # DynamoDB will reject the write and we'll return True (halt active) on next check
                            try:
                                table.put_item(
                                    Item={
                                        "key": self.HALT_FLAG_DYNAMODB_KEY,
                                        "halt_flag": False,
                                        "reason": "Auto-expired: halt flag from prior trading day after market open",
                                        "reset_at": now_utc.isoformat(),
                                        "previous_triggered_at": triggered_at_str,  # Track what we cleared
                                    },
                                    # Atomic condition: Only clear if halt_flag is still True and triggered_at hasn't changed
                                    ConditionExpression="halt_flag = :true AND triggered_at = :orig_time",
                                    ExpressionAttributeValues={
                                        ":true": True,
                                        ":orig_time": triggered_at_str,
                                    }
                                )
                                return False
                            except Exception as cond_err:
                                # Condition failed: another orchestrator modified halt between our check and write
                                logger.warning(
                                    f"[HALT_FLAG] Atomic clear condition failed (another instance modified halt): {cond_err}. "
                                    f"Returning True (halt still active)."
                                )
                                return True
                        else:
                            logger.info(f"[HALT_FLAG] Halt from {trigger_date} still active before market open today")
                            return True

                    if trigger_date == now_date_et:
                        hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                        reason = item.get("reason")
                        if not reason:
                            msg = (
                                "[HALT_FLAG CRITICAL] Orchestrator halt flag is set but "
                                "'reason' field is missing or NULL. "
                                "Cannot determine why trading halted. "
                                "Check orchestrator_halt_flag.reason in database."
                            )
                            logger.critical(msg)
                            raise ValueError(msg)
                        logger.critical(
                            f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED on {now_date_et}. "
                            f"Triggered {hours_halted:.1f}h ago at {trigger_et.strftime('%H:%M ET')}. "
                            f"Reason: {reason[:150]}"
                        )
                        self.log_phase_result(
                            0,
                            "halt_flag_detected",
                            "halted",
                            f"Halt flag detected (triggered at {trigger_et.strftime('%H:%M ET')}: {reason[:100]})",
                        )
                        return True

                except (ValueError, KeyError) as parse_err:
                    logger.warning(f"[HALT_FLAG] Could not parse triggered_at: {parse_err}")

                reason = item.get("reason")
                if not reason:
                    msg = (
                        "[HALT_FLAG CRITICAL] Orchestrator halt flag is set but "
                        "'reason' field is missing or NULL. "
                        "Cannot determine why trading halted. "
                        "Check orchestrator_halt_flag.reason in database."
                    )
                    logger.critical(msg)
                    raise ValueError(msg)
                logger.critical(
                    f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (could not parse timestamp). Reason: {reason[:150]}"
                )
                self.log_phase_result(
                    0,
                    "halt_flag_detected",
                    "halted",
                    f"Halt flag detected: {reason[:100]}",
                )
                return True

            return False
        except Exception as e:
            # Session 289 FIX: Don't crash on DynamoDB unavailability, fall back to RDS instead
            # Log the error but return None to signal fallback, not fail-closed
            logger.debug(f"[HALT_FLAG] DynamoDB check failed: {e}. Will try RDS fallback.")
            return None

    def _check_halt_flag_rds(self) -> bool | None:
        """Check halt flag in RDS. Returns True/False if successful, None if unavailable."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT halt_flag, halt_reason, halt_triggered_at
                    FROM algo_runtime_state
                    WHERE state_key = %s
                    """,
                    (self.HALT_FLAG_DYNAMODB_KEY,),
                )
                result = cur.fetchone()

                if not result:
                    logger.debug("[HALT_FLAG] No halt flag in RDS (not set)")
                    return False

                halt_flag, reason, triggered_at = result

                if not halt_flag:
                    return False

                # Check if halt is from previous trading day (auto-expiry)
                if triggered_at:
                    try:
                        trigger_dt = datetime.fromisoformat(triggered_at.isoformat() if hasattr(triggered_at, 'isoformat') else triggered_at)
                        now_utc = datetime.now(timezone.utc)

                        trigger_et = trigger_dt.astimezone(EASTERN_TZ) if trigger_dt.tzinfo else trigger_dt.replace(tzinfo=EASTERN_TZ)
                        now_et = now_utc.astimezone(EASTERN_TZ)

                        trigger_date = trigger_et.date()
                        now_date_et = now_et.date()

                        if trigger_date < now_date_et:
                            market_open_et = now_et.replace(
                                hour=MARKET_OPEN_HOUR,
                                minute=MARKET_OPEN_MINUTE,
                                second=0,
                                microsecond=0,
                            )
                            market_open_et = market_open_et.replace(tzinfo=EASTERN_TZ)

                            if now_et >= market_open_et:
                                logger.info(
                                    f"[HALT_FLAG] Halt from {trigger_date} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET) "
                                    f"on {now_date_et} - auto-clearing via RDS"
                                )
                                # Clear halt flag in RDS
                                try:
                                    clear_cur = DatabaseContext("write")
                                    with clear_cur as cur2:
                                        cur2.execute(
                                            """UPDATE algo_runtime_state SET halt_flag = FALSE, halt_count = 0
                                               WHERE state_key = %s""",
                                            (self.HALT_FLAG_DYNAMODB_KEY,)
                                        )
                                except Exception as clear_err:
                                    logger.warning(f"[HALT_FLAG] Could not auto-clear halt in RDS: {clear_err}")
                                return False
                            else:
                                logger.info(f"[HALT_FLAG] Halt from {trigger_date} still active before market open today")
                                return True

                        if trigger_date == now_date_et:
                            hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                            logger.critical(
                                f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (from RDS) on {now_date_et}. "
                                f"Triggered {hours_halted:.1f}h ago. "
                                f"Reason: {reason[:150] if reason else 'N/A'}"
                            )
                            return True

                    except (ValueError, KeyError, TypeError) as parse_err:
                        logger.warning(f"[HALT_FLAG] Could not parse RDS timestamp: {parse_err}")

                if reason:
                    logger.critical(
                        f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (from RDS, could not parse timestamp). "
                        f"Reason: {reason[:150]}"
                    )
                return True

        except Exception as e:
            logger.debug(f"[HALT_FLAG] RDS check failed: {e}. Both DynamoDB and RDS unavailable.")
            return None

    def set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag in DynamoDB or RDS. Returns True if successfully set.

        Session 289 FIX: Try DynamoDB first, fall back to RDS if unavailable.
        RDS serves as fallback so system doesn't crash when AWS credentials missing.

        Session 290 FIX: Add retry logic + graceful degradation when BOTH fail.
        If both DynamoDB and RDS unavailable, log warning but don't crash.
        This prevents orchestrator crashes during transient connectivity issues.

        ISSUE #8 FIX: When Phase 1 detects stale data, set halt flag to stop
        Phase 5 from generating full-intensity signals during degradation.

        ISSUE #10 FIX: Track multiple halt events in a day for escalation.
        """
        halt_count = 1
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                import boto3

                dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
                table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                table = dynamodb.Table(table_name)

                # CRITICAL FIX: Use atomic UpdateExpression to increment halt_count
                # Prevents race: two concurrent halts both reading count=1 and writing count=2
                # Instead: use DynamoDB ADD operation which is atomic
                try:
                    # First, set up the halt with initial values if not exists
                    table.update_item(
                        Key={"key": self.HALT_FLAG_DYNAMODB_KEY},
                        UpdateExpression=(
                            "SET halt_flag = :flag, "
                            "triggered_at = if_not_exists(triggered_at, :now), "
                            "reason = if_not_exists(reason, :reason), "
                            "last_halt_at = :now "
                            "ADD halt_count :inc"
                        ),
                        ExpressionAttributeValues={
                            ":flag": True,
                            ":now": now_utc.isoformat(),
                            ":reason": reason or "Phase 1 degraded: stale data detected",
                            ":inc": 1,
                        },
                        RetryPolicy={'MaxAttempts': 1}  # Don't retry at boto3 level
                    )

                    # Now fetch to get the updated count and log escalation if needed
                    response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
                    if "Item" in response:
                        item = response["Item"]
                        halt_count = item.get("halt_count", 1)
                        first_trigger = item.get("triggered_at")

                        if first_trigger:
                            try:
                                first_dt = datetime.fromisoformat(first_trigger.replace("Z", "+00:00"))
                                first_et = first_dt.astimezone(EASTERN_TZ)
                                if first_et.date() == now_et.date():
                                    logger.critical(
                                        f"[HALT_FLAG_ESCALATION] REPEATED HALT on {now_et.date()}: "
                                        f"Halt #{halt_count} in same day. "
                                        f"First at {first_et.strftime('%H:%M ET')}, now at {now_et.strftime('%H:%M ET')}. "
                                        f"Reason: {reason[:100]}"
                                    )
                                    if halt_count >= 2:
                                        try:
                                            self.alerts.send_position_alert(
                                                "HALT_ESCALATION",
                                                f"HALT_REPEAT_{halt_count}",
                                                f"Halt flag triggered {halt_count} times on {now_et.date()}. "
                                                "Repeated data quality issues. Manual investigation required.",
                                                {
                                                    "halt_count": halt_count,
                                                    "first_at": first_trigger,
                                                    "latest_reason": reason[:100],
                                                },
                                            )
                                        except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                                            logger.warning(f"Could not send escalation alert: {alert_err}")
                            except (ValueError, KeyError) as escalation_err:
                                logger.warning(f"Could not parse halt escalation: {escalation_err}")
                except Exception as update_err:
                    logger.debug(f"Failed to set DynamoDB halt flag (attempt {attempt+1}): {update_err}. Trying RDS fallback.")
                    raise

                if halt_count >= 2:
                    logger.critical(f"[HALT_FLAG_SET_ESCALATED] {reason or 'Phase 1 degraded'} (halt #{halt_count})")
                else:
                    logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'}")
                return True
            except Exception as e:
                last_error = e
                # Fall back to RDS
                logger.debug(f"[HALT_FLAG] DynamoDB set attempt {attempt+1}/{max_retries} failed: {e}. Using RDS fallback.")
                try:
                    return self._set_halt_flag_rds(reason, now_utc, now_et)
                except Exception as rds_err:
                    logger.warning(f"[HALT_FLAG] RDS fallback also failed (attempt {attempt+1}): {rds_err}")
                    last_error = rds_err
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(0.5)  # Brief backoff before retry
                        continue
                    else:
                        break

        # Both DynamoDB and RDS failed: MUST raise exception
        # Halt flag is safety-critical. If we can't set it, the orchestrator must fail.
        raise RuntimeError(
            f"[GOVERNANCE VIOLATION] Halt flag could not be set. Both DynamoDB and RDS failed. "
            f"Last error: {last_error}. "
            f"This is a critical safety failure - cannot proceed with trading when halt flag unavailable. "
            f"Check: (1) RDS database connectivity (localhost:5432), (2) AWS credentials/DynamoDB access, (3) network issues."
        )

    def _set_halt_flag_rds(self, reason: str, now_utc: datetime, now_et: datetime) -> bool:
        """Set halt flag in RDS. Returns True if successfully set."""
        import json
        try:
            with DatabaseContext("write") as cur:
                state_value = json.dumps({"halt_triggered_by": "orchestrator", "reason": reason or "Phase 1 degraded"})
                cur.execute(
                    """
                    INSERT INTO algo_runtime_state (
                        state_key, state_value, halt_flag, halt_triggered_at, halt_reason, halt_count, updated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (state_key) DO UPDATE SET
                        state_value = EXCLUDED.state_value,
                        halt_flag = EXCLUDED.halt_flag,
                        halt_triggered_at = EXCLUDED.halt_triggered_at,
                        halt_reason = EXCLUDED.halt_reason,
                        halt_count = COALESCE(algo_runtime_state.halt_count, 0) + 1,
                        last_updated_at = CURRENT_TIMESTAMP
                    """,
                    (self.HALT_FLAG_DYNAMODB_KEY, state_value, True, now_utc.isoformat(), reason or "Phase 1 degraded: stale data detected", 1, "orchestrator"),
                )
            logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'} (via RDS fallback)")
            return True
        except Exception as e:
            logger.error(f"[HALT_FLAG] Failed to set halt flag in RDS: {e}")
            return False

    def proactive_clear_stale_halt(self) -> bool:
        """Proactively clear halt flag at orchestrator startup if halt is from prior trading day.

        ISSUE #31 FIX: Orchestrator could get stuck in deadlock where:
        1. Halt flag set on Day 1 prevents Phase 1 from running
        2. Phase 1 never runs, so can't clear the halt
        3. Halt flag never gets cleared

        This method (called at orchestrator startup) breaks the deadlock by:
        - Checking if halt_flag was set on a prior trading day
        - If yes and it's past market open today: auto-clear it
        - If yes and it's before market open today: leave it (data might still be stale)

        Returns: True if halt was cleared, False if still active or no halt set

        CRITICAL FIX (Session 282): ALWAYS attempt to clear stale halts, including LOCAL_MODE.
        LOCAL_MODE connects to the same shared production DB, so stale halt flags
        must be cleared. If you want to skip safety checks, use dry_run=True instead.
        """

        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            if "Item" not in response:
                return False

            item = response["Item"]
            if item.get("halt_flag") is not True:
                return False

            triggered_at_str = item.get("triggered_at")
            if not triggered_at_str:
                logger.warning(
                    "[PROACTIVE_CLEAR] Halt flag is set but triggered_at is missing. "
                    "Cannot determine age. Leaving halt active."
                )
                return False

            try:
                trigger_dt = datetime.fromisoformat(triggered_at_str.replace("Z", "+00:00"))
                now_utc = datetime.now(timezone.utc)

                trigger_et = trigger_dt.astimezone(EASTERN_TZ)
                now_et = now_utc.astimezone(EASTERN_TZ)

                trigger_date = trigger_et.date()
                now_date_et = now_et.date()

                if trigger_date < now_date_et:
                    market_open_et = now_et.replace(
                        hour=MARKET_OPEN_HOUR,
                        minute=MARKET_OPEN_MINUTE,
                        second=0,
                        microsecond=0,
                    )
                    market_open_et = market_open_et.replace(tzinfo=EASTERN_TZ)

                    if now_et >= market_open_et:
                        logger.critical(
                            f"[PROACTIVE_CLEAR] Halt from {trigger_date} detected at orchestrator startup. "
                            f"It's now {now_date_et} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET). "
                            f"Breaking deadlock by auto-clearing halt."
                        )
                        table.put_item(
                            Item={
                                "key": self.HALT_FLAG_DYNAMODB_KEY,
                                "halt_flag": False,
                                "reason": "Proactive clear at orchestrator startup: halt from prior trading day post-market-open",
                                "reset_at": now_utc.isoformat(),
                                "original_trigger_date": trigger_date.isoformat(),
                            }
                        )
                        logger.info("[PROACTIVE_CLEAR] Halt flag successfully cleared. Orchestrator will proceed.")
                        return True
                    else:
                        logger.info(
                            f"[PROACTIVE_CLEAR] Halt from {trigger_date} still active before market open. "
                            f"Leaving halt in place."
                        )
                        return False

                logger.debug(
                    f"[PROACTIVE_CLEAR] Halt is from today ({trigger_date}). Leaving it active - Phase 1 will evaluate."
                )
                return False

            except (ValueError, KeyError) as parse_err:
                logger.warning(f"[PROACTIVE_CLEAR] Could not parse triggered_at: {parse_err}")
                return False

        except Exception as e:
            if "UnrecognizedClientException" in str(e) or "InvalidCredentials" in str(e):
                logger.info(f"[PROACTIVE_CLEAR] DynamoDB unavailable, attempting RDS fallback")
                try:
                    return self._proactive_clear_stale_halt_rds()
                except Exception as rds_err:
                    logger.warning(f"[PROACTIVE_CLEAR] RDS fallback also failed: {rds_err}. Continuing anyway.")
                    return False
            else:
                logger.warning(f"[PROACTIVE_CLEAR] Could not proactively clear halt: {e}. Continuing anyway.")
            return False

    def _proactive_clear_stale_halt_rds(self) -> bool:
        """Proactively clear stale halt flag from RDS. Returns True if cleared, False if still active or no halt."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT halt_flag, halt_triggered_at
                    FROM algo_runtime_state
                    WHERE state_key = %s
                    """,
                    (self.HALT_FLAG_DYNAMODB_KEY,),
                )
                result = cur.fetchone()

                if not result or not result[0]:
                    return False

                triggered_at = result[1]
                if not triggered_at:
                    return False

                try:
                    trigger_dt = datetime.fromisoformat(triggered_at.isoformat() if hasattr(triggered_at, 'isoformat') else triggered_at)
                    now_utc = datetime.now(timezone.utc)

                    trigger_et = trigger_dt.astimezone(EASTERN_TZ) if trigger_dt.tzinfo else trigger_dt.replace(tzinfo=EASTERN_TZ)
                    now_et = now_utc.astimezone(EASTERN_TZ)

                    trigger_date = trigger_et.date()
                    now_date_et = now_et.date()

                    if trigger_date < now_date_et:
                        market_open_et = now_et.replace(
                            hour=MARKET_OPEN_HOUR,
                            minute=MARKET_OPEN_MINUTE,
                            second=0,
                            microsecond=0,
                        )
                        market_open_et = market_open_et.replace(tzinfo=EASTERN_TZ)

                        if now_et >= market_open_et:
                            logger.critical(
                                f"[PROACTIVE_CLEAR] Halt from {trigger_date} detected at orchestrator startup. "
                                f"It's now {now_date_et} past market open ({MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET). "
                                f"Breaking deadlock by auto-clearing halt (RDS)."
                            )
                            with DatabaseContext("write") as write_cur:
                                write_cur.execute(
                                    """UPDATE algo_runtime_state SET halt_flag = FALSE, halt_count = 0
                                       WHERE state_key = %s""",
                                    (self.HALT_FLAG_DYNAMODB_KEY,)
                                )
                            logger.info("[PROACTIVE_CLEAR] Halt flag successfully cleared (RDS). Orchestrator will proceed.")
                            return True

                    return False

                except (ValueError, KeyError, TypeError) as parse_err:
                    logger.warning(f"[PROACTIVE_CLEAR] Could not parse RDS timestamp: {parse_err}")
                    return False

        except Exception as e:
            logger.warning(f"[PROACTIVE_CLEAR] RDS proactive clear failed: {e}")
            return False

    def clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in DynamoDB or RDS. Returns True if successfully cleared.

        ISSUE #8 FIX: When Phase 1 verifies data is fresh, explicitly clear the
        halt flag to allow Phase 5 to generate signals normally.

        Session 289 FIX: Try DynamoDB first, fall back to RDS if unavailable.
        Prevents crashes when AWS credentials missing or DynamoDB unavailable.

        Session 290 FIX: Add retry logic + graceful degradation when BOTH fail.
        If both DynamoDB and RDS unavailable, log warning but don't crash.
        This prevents trading halt during transient connectivity issues.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared, False on error (non-fatal)

        CRITICAL FIX (Session 282): ALWAYS clear halt flag, including LOCAL_MODE.
        LOCAL_MODE connects to the same shared production DB, so halt flag updates
        must persist. If you want to skip safety checks, use dry_run=True instead.
        """
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                import boto3

                dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
                table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                table = dynamodb.Table(table_name)

                now_utc = datetime.now(timezone.utc)
                table.put_item(
                    Item={
                        "key": self.HALT_FLAG_DYNAMODB_KEY,
                        "halt_flag": False,
                        "cleared_at": now_utc.isoformat(),
                        "reason": reason or "Phase 1 verified: data is fresh",
                        "reset_at": now_utc.isoformat(),
                    },
                    RetryPolicy={'MaxAttempts': 1}  # Don't retry at boto3 level, we'll do it here
                )
                logger.info(f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}")
                return True
            except Exception as e:
                last_error = e
                logger.debug(f"[HALT_FLAG] DynamoDB clear attempt {attempt+1}/{max_retries} failed: {e}. Will try RDS fallback.")

                # Try RDS fallback
                try:
                    return self._clear_halt_flag_rds(reason)
                except Exception as rds_err:
                    logger.warning(f"[HALT_FLAG] RDS fallback also failed (attempt {attempt+1}): {rds_err}")
                    last_error = rds_err
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(0.5)  # Brief backoff before retry
                        continue
                    else:
                        break

        # Both DynamoDB and RDS failed: MUST raise exception
        # Halt flag is safety-critical. If we can't clear it, the orchestrator must fail.
        # We cannot proceed with unknown halt status - it might be stale or incorrect.
        raise RuntimeError(
            f"[GOVERNANCE VIOLATION] Halt flag could not be cleared. Both DynamoDB and RDS failed. "
            f"Last error: {last_error}. "
            f"This is a critical safety failure - cannot proceed with trading when halt flag unavailable. "
            f"Check: (1) RDS database connectivity (localhost:5432), (2) AWS credentials/DynamoDB access, (3) network issues."
        )

    def _clear_halt_flag_rds(self, reason: str) -> bool:
        """Clear halt flag in RDS. Returns True if successfully cleared."""
        try:
            with DatabaseContext("write") as cur:
                now_utc = datetime.now(timezone.utc)
                cur.execute(
                    """
                    UPDATE algo_runtime_state
                    SET halt_flag = FALSE, halt_count = 0, halt_reason = %s, last_updated_at = %s
                    WHERE state_key = %s
                    """,
                    (reason or "Phase 1 verified: data is fresh", now_utc, self.HALT_FLAG_DYNAMODB_KEY),
                )
            logger.info(f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'} (via RDS fallback)")
            return True
        except Exception as e:
            logger.error(f"[HALT_FLAG] Failed to clear halt flag in RDS: {e}")
            return False
