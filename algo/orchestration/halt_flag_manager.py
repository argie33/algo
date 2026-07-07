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
        """Check for halt flag in DynamoDB. Returns True if halt was requested.

        Uses DynamoDB instead of /tmp to work in Lambda where /tmp is ephemeral.
        SECURITY: If DynamoDB is unreachable, emits CloudWatch alarm metric.

        ISSUE #8 FIX: Halt flag persists through entire trading day (9:30 AM - 4:00 PM ET)
        to prevent Phase 5 from generating signals with stale data set by early morning
        Phase 1. Auto-expires only at market open of next trading day (9:30 AM ET).

        Timeline example:
        - 2:30 AM: Loaders detect stale data -> Phase 1 sets halt_flag with triggered_at=2:30 AM
        - 9:30 AM, 1 PM, 3 PM, 5:30 PM: Orchestrator runs check halt_flag -> still active (same day)
        - 9:30 AM NEXT DAY: Auto-clears halt_flag at market open (new trading day)
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
                                f"on {now_date_et} — auto-clearing"
                            )
                            table.put_item(
                                Item={
                                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                                    "halt_flag": False,
                                    "reason": "Auto-expired: halt flag from prior trading day after market open",
                                    "reset_at": now_utc.isoformat(),
                                }
                            )
                            return False
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
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.critical(f"[CRITICAL] Could not check halt flag in DynamoDB: {e}")
            logger.critical("[CRITICAL] FAILING CLOSED: Treating DynamoDB unavailability as halt condition for safety")

            try:
                self.alerts.send_position_alert(
                    "DYNAMODB",
                    "HALT_CHECK_UNAVAILABLE",
                    "DynamoDB halt flag check failed. Emergency halt mechanism DISABLED. Trading halted as fail-safe. "
                    f"Error: {str(e)[:200]}",
                    {"error": str(e)[:200], "action": "manual_intervention_required"},
                )
            except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                logger.warning(f"Could not send DynamoDB unavailability alert: {alert_err}")

            try:
                from algo.reporting import MetricsPublisher

                MetricsPublisher().add_metric("DynamoDBHaltCheckFailure", 1, unit="Count")
            except (ValueError, ZeroDivisionError, TypeError) as metric_err:
                logger.warning(f"Could not emit halt check failure metric: {metric_err}")

            return True

    def set_halt_flag(self, reason: str = "") -> bool:
        """Set halt flag in DynamoDB. Returns True if successfully set.

        ISSUE #8 FIX: When Phase 1 detects stale data, set halt flag to stop
        Phase 5 from generating full-intensity signals during degradation.

        ISSUE #10 FIX: Track multiple halt events in a day for escalation.
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
            table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
            table = dynamodb.Table(table_name)

            now_utc = datetime.now(timezone.utc)
            now_et = now_utc.astimezone(EASTERN_TZ)

            halt_count = 1
            halt_escalated = False
            response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
            if "Item" in response:
                item = response["Item"]
                if item.get("halt_flag") is True:
                    first_trigger = item.get("triggered_at")
                    if first_trigger:
                        try:
                            first_dt = datetime.fromisoformat(first_trigger.replace("Z", "+00:00"))
                            first_et = first_dt.astimezone(EASTERN_TZ)
                            if first_et.date() == now_et.date():
                                prev_halt_count = item.get("halt_count")
                                if prev_halt_count is None:
                                    raise RuntimeError(
                                        "[HALT_FLAG_ESCALATION CRITICAL] Previous halt count is NULL. "
                                        "Cannot properly escalate repeated daily halts without halt counter. "
                                        "DynamoDB halt_flag record corrupted."
                                    )
                                halt_count = prev_halt_count + 1
                                halt_escalated = True
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
                                except (
                                    ValueError,
                                    ZeroDivisionError,
                                    TypeError,
                                ) as alert_err:
                                    logger.warning(f"Could not send escalation alert: {alert_err}")
                        except (ValueError, KeyError) as escalation_err:
                            logger.warning(f"Could not check halt escalation: {escalation_err}")

            table.put_item(
                Item={
                    "key": self.HALT_FLAG_DYNAMODB_KEY,
                    "halt_flag": True,
                    "triggered_at": now_utc.isoformat(),
                    "reason": reason or "Phase 1 degraded: stale data detected",
                    "halt_count": halt_count,
                }
            )

            if halt_escalated and halt_count >= 2:
                logger.critical(f"[HALT_FLAG_SET_ESCALATED] {reason or 'Phase 1 degraded'} (halt #{halt_count})")
            else:
                logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'}")
            return True
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

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
                    f"[PROACTIVE_CLEAR] Halt is from today ({trigger_date}). Leaving it active — Phase 1 will evaluate."
                )
                return False

            except (ValueError, KeyError) as parse_err:
                logger.warning(f"[PROACTIVE_CLEAR] Could not parse triggered_at: {parse_err}")
                return False

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"[PROACTIVE_CLEAR] Could not proactively clear halt: {e}. Continuing anyway.")
            return False

    def clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in DynamoDB. Returns True if successfully cleared.

        ISSUE #8 FIX: When Phase 1 verifies data is fresh, explicitly clear the
        halt flag to allow Phase 5 to generate signals normally.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared, False on error
        """
        try:
            import boto3

            dynamodb = boto3.resource("dynamodb")
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
                }
            )
            logger.info(f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}")
            return True
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e
