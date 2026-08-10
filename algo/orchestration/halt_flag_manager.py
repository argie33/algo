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
import zlib
from datetime import datetime, timezone
from typing import Any

from utils.db import DatabaseContext
from utils.infrastructure import EASTERN_TZ, MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE

logger = logging.getLogger(__name__)


class HaltFlagManager:
    """Manage halt flag state in DynamoDB with auto-expiry and escalation tracking."""

    HALT_FLAG_DYNAMODB_KEY = "orchestrator_halt"

    # BUG FIX: the four advisory-lock call sites below used to compute
    # `hash(self.HALT_FLAG_DYNAMODB_KEY) % (2**31)` per call. Python randomizes str
    # hashing per-process by default (PYTHONHASHSEED, unset anywhere in this repo's
    # Docker/Lambda/CI config) - confirmed live: three separate `python -c
    # "hash('orchestrator_halt')"` invocations returned three different values. Every
    # "RACE CONDITION FIX" comment on these methods claims "all instances wait on same
    # lock", but concurrent orchestrator processes (the exact Lambda/ECS scenario these
    # comments describe) each derive a DIFFERENT lock_id for the identical logical
    # resource, so pg_advisory_lock never actually serializes them - a silent no-op.
    # zlib.crc32 is not seed-randomized (verified stable across process invocations),
    # matching the fixed-constant pattern already used elsewhere for the same reason
    # (see PORTFOLIO_SNAPSHOT_LOCK_ID in position_sizer.py / reconciliation.py).
    HALT_FLAG_LOCK_ID = zlib.crc32(HALT_FLAG_DYNAMODB_KEY.encode()) % (2**31)

    def __init__(self, alerts: Any, log_phase_result: Any) -> None:
        """Initialize with alert manager and phase logging callback.

        Args:
            alerts: AlertManager instance for escalation
            log_phase_result: Callback to log phase results
        """
        self.alerts = alerts
        self.log_phase_result = log_phase_result
        # Instance variable allows independent logging for each orchestrator run
        self._dynamodb_unavailable_logged: bool = False

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
            if dynamodb_result:
                self._alert_halt_detected("DynamoDB")
            return dynamodb_result

        # Fall back to RDS if DynamoDB unavailable (log only once per run)
        if not self._dynamodb_unavailable_logged:
            logger.critical("[HALT_FLAG] DynamoDB unavailable, falling back to RDS for halt flag read")
            self._dynamodb_unavailable_logged = True

        rds_result = self._check_halt_flag_rds()
        if rds_result is not None:
            if rds_result:
                self._alert_halt_detected("RDS fallback")
            return rds_result

        # Both unavailable: fail-closed (assume halt)
        logger.critical("[HALT_FLAG] Both DynamoDB and RDS unavailable - failing closed for safety")
        self._alert_halt_detected("both DynamoDB and RDS unavailable - failing closed")
        return True

    def _alert_halt_detected(self, source: str) -> None:
        """Notify operators that trading is halted.

        Every OTHER halt-triggering path in this codebase alerts (see
        phase2_circuit_breakers.py, phase3_position_monitor.py) - this check-existing-halt
        path previously only logged CRITICAL to the application log, which nobody may ever
        read, so a halt detected here (e.g. set by a prior Phase 1 run, or a DynamoDB/RDS
        outage forcing fail-closed) could go unnoticed indefinitely. Best-effort: must never
        block or fail the halt check itself.
        """
        try:
            self.alerts.send_position_alert(
                "PORTFOLIO",
                "HALT_FLAG_ACTIVE",
                f"Orchestrator halt flag is active (detected via {source}). Trading is halted.",
            )
        except Exception as e:
            logger.error(f"[HALT_FLAG] Failed to send halt-detected alert (non-blocking): {e}")

    def _check_halt_flag_dynamodb(self) -> bool | None:
        """Check halt flag in DynamoDB. Returns True/False if successful, None if unavailable."""
        try:
            import boto3

            # Check if AWS credentials available - skip DynamoDB if not configured (local dev)
            if not os.environ.get("AWS_ACCESS_KEY_ID"):
                logger.debug("[HALT_FLAG] AWS credentials not configured - skipping DynamoDB, using RDS fallback")
                return None

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
            # BUG FOUND 2026-08-10 (companion to halt_flag_cleared_by_unrelated_phase_fix): see
            # _check_halt_flag_rds()'s identical fix for the full explanation - the
            # next-trading-day auto-expiry below used to clear ANY halt purely on calendar
            # rollover, with zero check of who set it. Fail closed on anything not explicitly
            # known-safe to expire this way.
            triggered_by = item.get("triggered_by")
            eligible_for_calendar_auto_expiry = triggered_by in (
                "phase1_data_freshness",
                "phase2_circuit_breaker",
            )
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

                        if now_et >= market_open_et and eligible_for_calendar_auto_expiry:
                            time_str = f"{MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}"
                            logger.info(
                                f"[HALT_FLAG] Halt from {trigger_date} (triggered_by={triggered_by}) past "
                                f"market open ({time_str} ET) on {now_date_et} - auto-clearing with atomic condition"
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
                                    # Atomic check: verify halt_flag=True and triggered_at unchanged
                                    ConditionExpression="halt_flag = :true AND triggered_at = :orig_time",
                                    ExpressionAttributeValues={
                                        ":true": True,
                                        ":orig_time": triggered_at_str,
                                    },
                                )
                                return False
                            except Exception as cond_err:
                                # Condition failed: another instance modified halt concurrently
                                logger.warning(
                                    f"[HALT_FLAG] Atomic clear condition failed "
                                    f"(another instance modified halt): {cond_err}. "
                                    "Returning True (halt still active)."
                                )
                                return True
                        else:
                            hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                            reason = item.get("reason") or "N/A"
                            not_eligible_note = (
                                "" if now_et < market_open_et else
                                f" NOT auto-expired: triggered_by={triggered_by!r} requires explicit clear "
                                "via scripts/manage_halt_flag.py or that phase's own logic."
                            )
                            logger.critical(
                                f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED on {now_date_et} (triggered prior "
                                f"trading day, still before {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} ET "
                                f"open, or not eligible for auto-expiry).{not_eligible_note} Triggered "
                                f"{hours_halted:.1f}h ago at {trigger_et.strftime('%H:%M ET')} "
                                f"on {trigger_date}. Reason: {reason[:150]}"
                            )
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
                            # Fail closed directly (return True) rather than raise: a raised
                            # exception here is caught by this same try's `except (ValueError,
                            # KeyError)` clause below (meant for genuine timestamp-parse errors),
                            # then re-raised via the duplicate check below and swallowed AGAIN by
                            # the outer `except Exception` as if DynamoDB were merely unavailable
                            # - which silently falls through to an unrelated RDS check that has no
                            # idea DynamoDB found an ACTIVE-but-corrupted halt flag, and could
                            # override it with a stale "not halted" answer. This is a genuine data
                            # integrity failure, not an infra outage - fail closed immediately.
                            return True
                        logger.critical(
                            f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED on {now_date_et}. "
                            f"Triggered {hours_halted:.1f}h ago at {trigger_et.strftime('%H:%M ET')}. "
                            f"Reason: {reason[:150]}"
                        )
                        self.log_phase_result(
                            0,
                            "halt_flag_detected",
                            "halted",
                            f"Halt flag detected (triggered at {trigger_et.strftime('%H:%M ET')}: {reason[:500]})",
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
                    # Fail closed directly - see the comment on the identical check above;
                    # raising here would be swallowed by the outer `except Exception` and
                    # silently deferred to an unrelated RDS fallback instead of failing closed.
                    return True
                logger.critical(
                    f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (could not parse timestamp). Reason: {reason[:150]}"
                )
                self.log_phase_result(
                    0,
                    "halt_flag_detected",
                    "halted",
                    f"Halt flag detected: {reason[:500]}",
                )
                return True

            return False
        except Exception as e:
            # Only fall back to RDS for AWS infrastructure failures (network, credentials, rate limit).
            # Programming errors (KeyError, AttributeError, etc.) should propagate to fail-closed.
            from botocore.exceptions import BotoCoreError, ClientError

            # Check if this is an AWS infrastructure error that warrants RDS fallback
            is_aws_error = isinstance(e, (BotoCoreError, ClientError))
            # Also allow "service unavailable" errors that might indicate transient issues
            is_service_unavailable = "ServiceUnavailable" in str(type(e).__name__) or "ConnectTimeout" in str(
                type(e).__name__
            )

            if is_aws_error or is_service_unavailable:
                logger.warning(
                    f"[HALT_FLAG] DynamoDB check failed with AWS infrastructure error: {type(e).__name__}: {e}. "
                    f"Attempting RDS fallback."
                )
                return None
            else:
                # Programming error (ValueError, AttributeError, etc.) - fail-closed
                logger.error(
                    f"[HALT_FLAG CRITICAL] Programming error in halt flag check: {type(e).__name__}: {e}. "
                    f"Failing closed to prevent accidental trading during error condition."
                )
                # Fail closed: assume halt flag is set if we can't verify it
                return True

    def _check_halt_flag_rds(self) -> bool | None:
        """Check halt flag in RDS. Returns True/False if successful, None if unavailable.

        RACE CONDITION FIX: Use advisory lock to serialize halt flag access across
        concurrent orchestrator instances. Without this lock, instance A could check
        halt state, find it clear, then instance B modifies it, leaving A with stale info.
        Advisory lock ensures atomic read-modify-write sequence.
        """
        try:
            with DatabaseContext("write") as cur:
                # Use advisory lock to serialize access to halt flag across concurrent instances
                # Lock ID is deterministic (hash of state key) so all instances wait on same lock
                lock_id = self.HALT_FLAG_LOCK_ID

                try:
                    # Acquire exclusive lock (blocks other instances until we release)
                    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))

                    # Now read halt flag - guaranteed no concurrent modifications during our read
                    cur.execute(
                        """
                        SELECT halt_flag, halt_reason, halt_triggered_at, state_value
                        FROM algo_runtime_state
                        WHERE state_key = %s
                        """,
                        (self.HALT_FLAG_DYNAMODB_KEY,),
                    )
                    result = cur.fetchone()

                    if not result:
                        logger.debug("[HALT_FLAG] No halt flag in RDS (not set)")
                        return False

                    halt_flag, reason, triggered_at, state_value = result

                    if not halt_flag:
                        return False

                    # BUG FOUND 2026-08-10 (companion to halt_flag_cleared_by_unrelated_phase_fix):
                    # the next-trading-day auto-expiry below cleared ANY halt purely on calendar
                    # rollover, with zero check of who set it - a far more reachable version of
                    # the exact bug already fixed for Phase 1's explicit clear_halt_flag() call,
                    # since check_halt_flag() is called from every phase's halt gate (Phase 8's
                    # entry check among them), not just Phase 1. A manual_operator halt (this
                    # codebase's only real kill switch) or a phase9_reconciliation_governance halt
                    # (unverified broker/DB portfolio state in real-money mode) would be silently
                    # wiped the very next trading day at market open regardless of whether the
                    # underlying investigation/reconciliation was ever actually resolved. Only
                    # phases whose halt is inherently tied to "today's" data staleness
                    # (phase1_data_freshness, phase2_circuit_breaker - both already get their own
                    # same-run self-clear when conditions improve) are safe to let expire on pure
                    # calendar rollover as a fallback; governance/manual halts require an explicit,
                    # human-reviewed clear regardless of how much time has passed.
                    triggered_by = None
                    if isinstance(state_value, str):
                        import json as _json

                        try:
                            state_value = _json.loads(state_value)
                        except (ValueError, TypeError):
                            state_value = None
                    if isinstance(state_value, dict):
                        triggered_by = state_value.get("halt_triggered_by")
                    # Fail closed on anything not explicitly known-safe to expire on calendar
                    # rollover alone - an unrecognized/legacy/missing tag (None, "orchestrator"
                    # from set_halt_flag()'s old default, or any future caller that doesn't tag
                    # itself) must NOT be treated as safe to auto-clear, exactly the same
                    # reasoning as not auto-clearing an unrecognized halt in
                    # orchestrator.py's phase_1_data_freshness().
                    eligible_for_calendar_auto_expiry = triggered_by in (
                        "phase1_data_freshness",
                        "phase2_circuit_breaker",
                    )

                    # Check if halt is from previous trading day (auto-expiry)
                    if triggered_at:
                        try:
                            trigger_dt = datetime.fromisoformat(
                                triggered_at.isoformat() if hasattr(triggered_at, "isoformat") else triggered_at
                            )
                            now_utc = datetime.now(timezone.utc)

                            # _set_halt_flag_rds writes halt_triggered_at as now_utc.isoformat() - a
                            # genuinely UTC value - into a `timestamp without time zone` column.
                            # Confirmed live: Postgres's cast from a tz-aware ISO string into that
                            # column type drops the offset but keeps the wall-clock digits as-is
                            # (does NOT convert via the session timezone), so the naive value read
                            # back here is UTC digits, not Eastern. Mislabeling it as Eastern via
                            # .replace(tzinfo=EASTERN_TZ) shifted the interpreted instant by the
                            # ET-UTC offset (4-5h) - enough to misclassify trigger_date near
                            # midnight ET. It also left `trigger_dt` itself naive, so the
                            # now_utc - trigger_dt subtraction below crashed with TypeError on every
                            # same-day active halt (confirmed live), caught by the broad except
                            # below and silently dropping the halt's real reason/duration from the
                            # CRITICAL log in favor of a generic "could not parse timestamp" warning.
                            trigger_dt = trigger_dt if trigger_dt.tzinfo else trigger_dt.replace(tzinfo=timezone.utc)
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

                                if now_et >= market_open_et and eligible_for_calendar_auto_expiry:
                                    time_str = f"{MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}"
                                    logger.info(
                                        f"[HALT_FLAG] Halt from {trigger_date} (triggered_by={triggered_by}) past "
                                        f"market open ({time_str} ET) on {now_date_et} - auto-clearing via RDS"
                                    )
                                    # Clear halt flag in RDS (still holding advisory lock - atomic operation)
                                    try:
                                        cur.execute(
                                            """UPDATE algo_runtime_state SET halt_flag = FALSE, halt_count = 0
                                               WHERE state_key = %s""",
                                            (self.HALT_FLAG_DYNAMODB_KEY,),
                                        )
                                    except Exception as clear_err:
                                        logger.warning(f"[HALT_FLAG] Could not auto-clear halt in RDS: {clear_err}")
                                    return False
                                elif now_et >= market_open_et:
                                    hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                                    logger.critical(
                                        f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (from RDS) on {now_date_et} "
                                        f"(triggered_by={triggered_by!r} - not eligible for calendar auto-expiry, "
                                        f"requires explicit clear via scripts/manage_halt_flag.py or that phase's "
                                        f"own logic). Triggered {hours_halted:.1f}h ago at "
                                        f"{trigger_et.strftime('%H:%M ET')} on {trigger_date}. "
                                        f"Reason: {reason[:150] if reason else 'N/A'}"
                                    )
                                    return True
                                else:
                                    hours_halted = (now_utc - trigger_dt).total_seconds() / 3600
                                    logger.critical(
                                        f"[HALT_FLAG_ACTIVE] HALT FLAG DETECTED (from RDS) on {now_date_et} "
                                        f"(triggered prior trading day, still before {MARKET_OPEN_HOUR}:"
                                        f"{MARKET_OPEN_MINUTE:02d} ET open). Triggered {hours_halted:.1f}h ago "
                                        f"at {trigger_et.strftime('%H:%M ET')} on {trigger_date}. "
                                        f"Reason: {reason[:150] if reason else 'N/A'}"
                                    )
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

                finally:
                    # Always release advisory lock, even if exception occurred
                    try:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    except Exception as unlock_err:
                        logger.warning(f"[HALT_FLAG] Could not release advisory lock: {unlock_err}")

        except Exception as e:
            logger.debug(f"[HALT_FLAG] RDS check failed: {e}. Both DynamoDB and RDS unavailable.")
            return None

    def get_halt_triggered_by(self) -> str | None:
        """Return the identity of whatever last set the currently-active halt flag, or None
        if no halt is active (or the identity can't be determined).

        BUG FOUND 2026-08-10 (live-reproduced): Phase 1's success path unconditionally called
        clear_halt_flag() whenever ITS OWN freshness check passed, regardless of which phase
        had actually set the currently-active halt or why. Phase 2 (circuit breaker) and
        Phase 9 (reconciliation governance - "unverified portfolio state before real order
        submission", the most dangerous case) both persist halts through this same mechanism.
        Phase 9's halt in particular is set at the END of a run specifically to block Phase 8
        from trading on the *next* run - but since Phase 1 runs before Phase 8 in that next
        run, its unconditional clear erased the Phase 9 halt before Phase 8 (or Phase 9 itself)
        ever got a chance to re-verify anything. Live-reproduced: manually set halt_flag=True
        with an unrelated reason, ran a full orchestrator invocation, confirmed via
        "[HALT_FLAG_CLEARED] Phase 1 verified data is fresh" that it was wiped regardless.

        Callers should only auto-clear a halt they recognize as their own (see
        orchestrator.py's phase_1_data_freshness, which now checks this before clearing).
        """
        try:
            import boto3

            if os.environ.get("LOCAL_MODE", "").lower() != "true" and os.environ.get("AWS_ACCESS_KEY_ID"):
                try:
                    dynamodb = boto3.resource("dynamodb")
                    table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                    table = dynamodb.Table(table_name)
                    response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
                    item = response.get("Item")
                    if item and item.get("halt_flag") is True:
                        triggered_by = item.get("triggered_by")
                        return str(triggered_by) if triggered_by is not None else None
                    if item is not None:
                        return None
                except Exception as e:
                    logger.debug(f"[HALT_FLAG] Could not read triggered_by from DynamoDB: {e}")

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT halt_flag, state_value FROM algo_runtime_state WHERE state_key = %s",
                    (self.HALT_FLAG_DYNAMODB_KEY,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                halt_flag, state_value = row
                if not halt_flag:
                    return None
                if isinstance(state_value, str):
                    import json

                    state_value = json.loads(state_value)
                if isinstance(state_value, dict):
                    return state_value.get("halt_triggered_by")
                return None
        except Exception as e:
            logger.warning(f"[HALT_FLAG] Could not determine halt_triggered_by: {e}. Treating as unknown origin.")
            return "unknown"

    def get_halt_reason(self) -> str | None:
        """Return the human-readable reason for the currently-active halt flag, or None if no
        halt is active (or the reason can't be determined).

        BUG FOUND 2026-08-10 (live-reproduced): OrchestratorPhaseExecutor.execute_phase()'s
        halt_check_fn skip path (for a phase skipped because the GLOBAL halt flag is active -
        as opposed to being skipped because an earlier phase IN THIS SAME RUN halted, which is
        a separate code path already fixed) built its PhaseResult with no `error` at all, since
        halt_check_fn only returns a bool. Phase 6's degraded-mode logging then read that None
        as "unknown reason" - reproducing the exact "Phase 5 halted: unknown reason" symptom
        this session was investigating, but for a halt this run never itself set (e.g. the
        manual operator kill switch, or any halt already active before this run started).
        Mirrors get_halt_triggered_by()'s structure/backend fallback so callers can build a
        real error message instead of a null one.
        """
        try:
            import boto3

            if os.environ.get("LOCAL_MODE", "").lower() != "true" and os.environ.get("AWS_ACCESS_KEY_ID"):
                try:
                    dynamodb = boto3.resource("dynamodb")
                    table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                    table = dynamodb.Table(table_name)
                    response = table.get_item(Key={"key": self.HALT_FLAG_DYNAMODB_KEY})
                    item = response.get("Item")
                    if item and item.get("halt_flag") is True:
                        reason = item.get("reason")
                        return str(reason) if reason is not None else None
                    if item is not None:
                        return None
                except Exception as e:
                    logger.debug(f"[HALT_FLAG] Could not read reason from DynamoDB: {e}")

            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT halt_flag, halt_reason FROM algo_runtime_state WHERE state_key = %s",
                    (self.HALT_FLAG_DYNAMODB_KEY,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                halt_flag, halt_reason = row
                if not halt_flag:
                    return None
                return str(halt_reason) if halt_reason is not None else None
        except Exception as e:
            logger.warning(f"[HALT_FLAG] Could not determine halt reason: {e}. Treating as unknown reason.")
            return None

    def set_halt_flag(self, reason: str = "", triggered_by: str = "orchestrator", force: bool = False) -> bool:
        """Set halt flag in DynamoDB or RDS. Returns True if successfully set.

        Session 289 FIX: Try DynamoDB first, fall back to RDS if unavailable.
        RDS serves as fallback so system doesn't crash when AWS credentials missing.

        Session 290 FIX: Add retry logic with RDS fallback when DynamoDB fails.

        Session 292 FIX: Session 290's "graceful degradation, don't crash" behavior
        contradicted the orchestrator's fail-fast expectation and produced a false
        sense of safety (halt flag silently unmanaged during trading). Both storage
        backends are now retried, but if BOTH fail this method RAISES - trading must
        not proceed with an unmanageable halt flag.

        ISSUE #8 FIX: When Phase 1 detects stale data, set halt flag to stop
        Phase 5 from generating full-intensity signals during degradation.

        ISSUE #10 FIX: Track multiple halt events in a day for escalation.

        BUG FOUND 2026-08-10 (live-reproduced): by default this is "sticky to the first
        trigger" (see _set_halt_flag_rds's docstring) so automated phases can't clobber each
        other's halt reason. But scripts/manage_halt_flag.py's manual operator --set relied on
        this SAME method - live-reproduced: with an automated halt already active (e.g.
        phase2_circuit_breaker), calling set_halt_flag(triggered_by="manual_operator") left
        triggered_by/reason as the ORIGINAL automated values; get_halt_triggered_by() still
        returned "phase2_circuit_breaker" afterward. manage_halt_flag.py printed "Trading is
        now halted until explicitly cleared" - a false assurance, since Phase 2's own self-clear
        logic (current_trigger == "phase2_circuit_breaker") would silently clear the flag - and
        the operator's manual halt with it - the next time Phase 2's circuit breaker recovers.
        `force=True` (used only by the manual kill switch) makes this call unconditionally
        overwrite triggered_by/reason/triggered_at so a human halt is never silently absorbed
        into - and later auto-cleared alongside - an automated one. halt_count still increments
        normally so escalation tracking (ISSUE #10) is unaffected.

        Raises: RuntimeError if both DynamoDB and RDS fail (safety-critical, no fallback left).
        """
        halt_count = 1
        now_utc = datetime.now(timezone.utc)
        now_et = now_utc.astimezone(EASTERN_TZ)
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                import boto3

                # Check LOCAL_MODE first - skip DynamoDB entirely in local development
                local_mode = os.environ.get("LOCAL_MODE", "").lower() == "true"
                if local_mode:
                    logger.debug("[HALT_FLAG] LOCAL_MODE enabled - skipping DynamoDB, using RDS fallback")
                    raise ValueError("LOCAL_MODE enabled - forcing RDS fallback")

                # Check if AWS credentials available - skip DynamoDB if not configured (local dev)
                if not os.environ.get("AWS_ACCESS_KEY_ID"):
                    logger.debug("[HALT_FLAG] AWS credentials not configured - skipping DynamoDB, using RDS fallback")
                    raise ValueError("AWS credentials missing - forcing RDS fallback")

                dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
                table_name = os.getenv("HALT_FLAG_TABLE", "algo_orchestrator_state")
                table = dynamodb.Table(table_name)

                # CRITICAL FIX: Use atomic UpdateExpression to increment halt_count
                # Prevents race: two concurrent halts both reading count=1 and writing count=2
                # Instead: use DynamoDB ADD operation which is atomic
                try:
                    # First, set up the halt with initial values if not exists.
                    # force=True (manual kill switch only) uses an unconditional SET instead of
                    # if_not_exists so a human halt always overwrites whatever automated halt
                    # was already active - see this method's docstring.
                    set_expr = (
                        "SET halt_flag = :flag, "
                        + ("triggered_at = :now, " if force else "triggered_at = if_not_exists(triggered_at, :now), ")
                        + ("reason = :reason, " if force else "reason = if_not_exists(reason, :reason), ")
                        + (
                            "triggered_by = :triggered_by, "
                            if force
                            else "triggered_by = if_not_exists(triggered_by, :triggered_by), "
                        )
                        + "last_halt_at = :now "
                        "ADD halt_count :inc"
                    )
                    table.update_item(
                        Key={"key": self.HALT_FLAG_DYNAMODB_KEY},
                        UpdateExpression=set_expr,
                        ExpressionAttributeValues={
                            ":flag": True,
                            ":now": now_utc.isoformat(),
                            ":reason": reason or "Phase 1 degraded: stale data detected",
                            ":triggered_by": triggered_by,
                            ":inc": 1,
                        },
                        RetryPolicy={"MaxAttempts": 1},  # Don't retry at boto3 level
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
                                    first_time = first_et.strftime("%H:%M ET")
                                    now_time = now_et.strftime("%H:%M ET")
                                    logger.critical(
                                        f"[HALT_FLAG_ESCALATION] REPEATED HALT on {now_et.date()}: "
                                        f"Halt #{halt_count} in same day. "
                                        f"First at {first_time}, now at {now_time}. "
                                        f"Reason: {reason[:500]}"
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
                                                    "latest_reason": reason[:500],
                                                },
                                            )
                                        except (ValueError, ZeroDivisionError, TypeError) as alert_err:
                                            logger.warning(f"Could not send escalation alert: {alert_err}")
                            except (ValueError, KeyError) as escalation_err:
                                logger.warning(f"Could not parse halt escalation: {escalation_err}")
                except Exception as update_err:
                    logger.debug(
                        f"Failed to set DynamoDB halt flag (attempt {attempt + 1}): {update_err}. Trying RDS fallback."
                    )
                    raise

                if halt_count >= 2:
                    logger.critical(f"[HALT_FLAG_SET_ESCALATED] {reason or 'Phase 1 degraded'} (halt #{halt_count})")
                else:
                    logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'}")
                return True
            except Exception as e:
                last_error = e
                # Fall back to RDS
                logger.debug(
                    f"[HALT_FLAG] DynamoDB set attempt {attempt + 1}/{max_retries} failed: {e}. Using RDS fallback."
                )
                try:
                    rds_result = self._set_halt_flag_rds(reason, now_utc, now_et, triggered_by, force)
                    if not rds_result:
                        last_error = RuntimeError("RDS returned False (write failed)")
                        logger.warning(f"[HALT_FLAG] RDS fallback returned False (attempt {attempt + 1})")
                        if attempt < max_retries - 1:
                            import time

                            time.sleep(0.5)  # Brief backoff before retry
                            continue
                        else:
                            break
                    return rds_result  # Return True on success
                except Exception as rds_err:
                    logger.warning(f"[HALT_FLAG] RDS fallback exception (attempt {attempt + 1}): {rds_err}")
                    last_error = rds_err
                    if attempt < max_retries - 1:
                        import time

                        time.sleep(0.5)  # Brief backoff before retry
                        continue
                    else:
                        break

        # Both DynamoDB and RDS failed: MUST raise exception
        # Halt flag is safety-critical. If we can't set it, the orchestrator must fail.
        error_msg = (
            f"[GOVERNANCE VIOLATION] Halt flag could not be set. Both DynamoDB and RDS failed. "
            f"Last error: {last_error}. "
            f"This is a critical safety failure - cannot proceed with trading when halt flag unavailable. "
            "Check: (1) RDS connectivity (localhost:5432), (2) AWS credentials/DynamoDB, (3) network."
        )
        raise RuntimeError(error_msg)

    def _set_halt_flag_rds(
        self,
        reason: str,
        now_utc: datetime,
        now_et: datetime,
        triggered_by: str = "orchestrator",
        force: bool = False,
    ) -> bool:
        """Set halt flag in RDS. Returns True if successfully set.

        RACE CONDITION FIX: Use advisory lock to serialize halt flag updates across
        concurrent orchestrator instances. Ensures halt_count increment is atomic.

        triggered_by identifies which check set this halt (e.g. "phase1_data_freshness",
        "phase2_circuit_breaker", "phase9_reconciliation_governance") - see
        get_halt_triggered_by()'s docstring for why this matters: Phase 1 must not
        auto-clear a halt some other phase set for an unrelated, possibly still-active
        reason. Sticky to the FIRST trigger within an active-halt window (matches the
        DynamoDB path's if_not_exists semantics for triggered_at/reason) - a second
        set_halt_flag() call while already halted (e.g. Phase 9 halting later in a run
        Phase 2 already halted) must not overwrite and hide the original cause.

        force=True (manual kill switch only, see set_halt_flag's docstring) breaks that
        stickiness deliberately: a human operator's halt must always become the attributed
        cause, never get silently absorbed into whatever automated halt was already active.
        """
        import json

        try:
            with DatabaseContext("write") as cur:
                # Use advisory lock to serialize access to halt flag
                lock_id = self.HALT_FLAG_LOCK_ID

                try:
                    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))

                    state_value = json.dumps({"halt_triggered_by": triggered_by, "reason": reason or "Phase 1 degraded"})
                    # force=True: unconditional overwrite (no CASE guard) - see docstring above.
                    preserve_guard = "algo_runtime_state.halt_flag" if not force else "FALSE"
                    cur.execute(
                        f"""
                        INSERT INTO algo_runtime_state (
                            state_key, state_value, halt_flag, halt_triggered_at, halt_reason, halt_count, updated_by
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (state_key) DO UPDATE SET
                            state_value = CASE WHEN {preserve_guard} THEN algo_runtime_state.state_value
                                               ELSE EXCLUDED.state_value END,
                            halt_flag = EXCLUDED.halt_flag,
                            halt_triggered_at = CASE WHEN {preserve_guard} THEN algo_runtime_state.halt_triggered_at
                                                     ELSE EXCLUDED.halt_triggered_at END,
                            halt_reason = CASE WHEN {preserve_guard} THEN algo_runtime_state.halt_reason
                                               ELSE EXCLUDED.halt_reason END,
                            halt_count = COALESCE(algo_runtime_state.halt_count, 0) + 1,
                            last_updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            self.HALT_FLAG_DYNAMODB_KEY,
                            state_value,
                            True,
                            now_utc.isoformat(),
                            reason or "Phase 1 degraded: stale data detected",
                            1,
                            triggered_by,
                        ),
                    )
                    logger.critical(f"[HALT_FLAG_SET] {reason or 'Phase 1 degraded: halt flag activated'} (via RDS fallback)")
                    return True
                finally:
                    try:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    except Exception as unlock_err:
                        logger.warning(f"[HALT_FLAG] Could not release advisory lock: {unlock_err}")

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

            # Check if AWS credentials available - skip DynamoDB if not configured (local dev)
            if not os.environ.get("AWS_ACCESS_KEY_ID"):
                logger.debug("[PROACTIVE_CLEAR] AWS credentials not configured - skipping DynamoDB, using RDS fallback")
                try:
                    return self._proactive_clear_stale_halt_rds()
                except Exception as rds_err:
                    logger.warning(
                        f"[PROACTIVE_CLEAR] RDS fallback failed: {rds_err}. "
                        "Could not clear stale halt (best-effort optimization). "
                        "Orchestrator will continue - halt will be checked via normal path."
                    )
                    return False

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

            # BUG FOUND 2026-08-10 (same bug class as check_halt_flag's companion fix, but
            # more dangerous here: this runs at orchestrator STARTUP, before Phase 1 or any
            # other phase gets a chance to reason about the halt at all. Unconditionally
            # auto-clearing on pure calendar rollover would silently wipe a manual_operator
            # kill-switch halt or a phase9_reconciliation_governance halt (unverified
            # broker/DB state before real-money order submission) the very next trading day,
            # defeating the exact protections added elsewhere in this file today.
            triggered_by = item.get("triggered_by")
            eligible_for_calendar_auto_expiry = triggered_by in (
                "phase1_data_freshness",
                "phase2_circuit_breaker",
            )

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

                    if now_et >= market_open_et and not eligible_for_calendar_auto_expiry:
                        logger.warning(
                            f"[PROACTIVE_CLEAR] Halt from {trigger_date} (triggered_by={triggered_by!r}) is past "
                            "market open but NOT eligible for calendar auto-expiry - requires explicit clear via "
                            "scripts/manage_halt_flag.py or that phase's own logic. Leaving halt active."
                        )
                        return False

                    if now_et >= market_open_et:
                        time_str = f"{MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}"
                        msg = (
                            f"Halt from {trigger_date} detected at startup. "
                            f"Now {now_date_et} past market open ({time_str} ET). "
                            "Breaking deadlock by auto-clearing."
                        )
                        logger.critical(f"[PROACTIVE_CLEAR] {msg}")
                        clear_reason = "Proactive clear at startup: halt from prior trading day post-market-open"
                        table.put_item(
                            Item={
                                "key": self.HALT_FLAG_DYNAMODB_KEY,
                                "halt_flag": False,
                                "reason": clear_reason,
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
                logger.info("[PROACTIVE_CLEAR] DynamoDB unavailable, attempting RDS fallback")
                try:
                    return self._proactive_clear_stale_halt_rds()
                except Exception as rds_err:
                    logger.warning(
                        f"[PROACTIVE_CLEAR] RDS fallback also failed: {rds_err}. "
                        "Could not clear stale halt (best-effort optimization). "
                        "Orchestrator will continue - halt will be checked via normal path."
                    )
                    return False
            else:
                logger.warning(
                    f"[PROACTIVE_CLEAR] Could not proactively clear halt: {e}. "
                    "Best-effort optimization failed. Orchestrator will continue - halt will be checked via normal path."
                )
            return False

    def _proactive_clear_stale_halt_rds(self) -> bool:
        """Proactively clear stale halt flag from RDS. Returns True if cleared, False if still active or no halt.

        RACE CONDITION FIX: Use advisory lock to serialize halt flag access at startup.
        Ensures read and clear are atomic even if called by multiple orchestrator instances.
        """
        try:
            with DatabaseContext("write") as cur:
                lock_id = self.HALT_FLAG_LOCK_ID

                try:
                    # Acquire lock before reading
                    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))

                    cur.execute(
                        """
                        SELECT halt_flag, halt_triggered_at, state_value
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

                    # Same bug class as _check_halt_flag_rds's companion fix, more dangerous
                    # here since this runs at orchestrator STARTUP before any phase reasoning -
                    # see proactive_clear_stale_halt()'s (DynamoDB) identical comment.
                    state_value = result[2]
                    if isinstance(state_value, str):
                        import json as _json

                        try:
                            state_value = _json.loads(state_value)
                        except (ValueError, TypeError):
                            state_value = None
                    triggered_by = state_value.get("halt_triggered_by") if isinstance(state_value, dict) else None
                    eligible_for_calendar_auto_expiry = triggered_by in (
                        "phase1_data_freshness",
                        "phase2_circuit_breaker",
                    )

                    try:
                        trigger_dt = datetime.fromisoformat(
                            triggered_at.isoformat() if hasattr(triggered_at, "isoformat") else triggered_at
                        )
                        now_utc = datetime.now(timezone.utc)

                        # Same root cause as _check_halt_flag_rds: _set_halt_flag_rds writes
                        # halt_triggered_at as now_utc.isoformat() - genuinely UTC - into a
                        # `timestamp without time zone` column, which stores the wall-clock
                        # digits verbatim (no session-timezone conversion). Mislabeling the
                        # naive value as Eastern instead of UTC shifts trigger_date forward by
                        # the ET-UTC offset (4-5h) - for a halt genuinely triggered late evening
                        # ET (e.g. 11 PM ET = past midnight UTC), this pushes trigger_date from
                        # "yesterday" to "today", so the previous-trading-day auto-clear branch
                        # below never fires. That branch exists specifically to break a startup
                        # deadlock (ISSUE #31) - silently defeating it for exactly the halts most
                        # likely to still be sitting there at the next morning's startup.
                        trigger_dt = trigger_dt if trigger_dt.tzinfo else trigger_dt.replace(tzinfo=timezone.utc)
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

                            if now_et >= market_open_et and not eligible_for_calendar_auto_expiry:
                                logger.warning(
                                    f"[PROACTIVE_CLEAR] Halt from {trigger_date} (triggered_by={triggered_by!r}) is "
                                    "past market open but NOT eligible for calendar auto-expiry - requires "
                                    "explicit clear via scripts/manage_halt_flag.py or that phase's own logic. "
                                    "Leaving halt active (RDS)."
                                )
                                return False

                            if now_et >= market_open_et:
                                time_str = f"{MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}"
                                logger.critical(
                                    f"[PROACTIVE_CLEAR] Halt from {trigger_date} detected at startup. "
                                    f"It's now {now_date_et} past market open ({time_str} ET). "
                                    "Breaking deadlock by auto-clearing halt (RDS)."
                                )
                                # Clear while still holding advisory lock (atomic operation)
                                cur.execute(
                                    """UPDATE algo_runtime_state SET halt_flag = FALSE, halt_count = 0
                                       WHERE state_key = %s""",
                                    (self.HALT_FLAG_DYNAMODB_KEY,),
                                )
                                logger.info(
                                    "[PROACTIVE_CLEAR] Halt flag successfully cleared (RDS). Orchestrator will proceed."
                                )
                                return True

                        return False

                    except (ValueError, KeyError, TypeError) as parse_err:
                        logger.warning(f"[PROACTIVE_CLEAR] Could not parse RDS timestamp: {parse_err}")
                        return False

                finally:
                    try:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    except Exception as unlock_err:
                        logger.warning(f"[HALT_FLAG] Could not release advisory lock: {unlock_err}")

        except Exception as e:
            logger.warning(f"[PROACTIVE_CLEAR] RDS proactive clear failed: {e}")
            return False

    def clear_halt_flag(self, reason: str = "") -> bool:
        """Clear halt flag in DynamoDB or RDS. Returns True if successfully cleared.

        ISSUE #8 FIX: When Phase 1 verifies data is fresh, explicitly clear the
        halt flag to allow Phase 5 to generate signals normally.

        Session 289 FIX: Try DynamoDB first, fall back to RDS if unavailable.
        Prevents crashes when AWS credentials missing or DynamoDB unavailable.

        Session 290 FIX: Add retry logic with RDS fallback when DynamoDB fails.

        Session 292 FIX: Session 290's "graceful degradation, don't crash" behavior
        contradicted the orchestrator's fail-fast expectation and produced a false
        sense of safety (halt flag silently unmanaged during trading). Both storage
        backends are now retried, but if BOTH fail this method RAISES - trading must
        not proceed with unknown/unmanageable halt status.

        Args:
            reason: Optional explanation for why halt was cleared

        Returns: True if successfully cleared via DynamoDB or RDS.

        Raises: RuntimeError if both DynamoDB and RDS fail (safety-critical, no fallback left).

        CRITICAL FIX (Session 282): ALWAYS clear halt flag, including LOCAL_MODE.
        LOCAL_MODE connects to the same shared production DB, so halt flag updates
        must persist. If you want to skip safety checks, use dry_run=True instead.
        """
        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                import boto3

                # Check LOCAL_MODE first - skip DynamoDB entirely in local development
                local_mode = os.environ.get("LOCAL_MODE", "").lower() == "true"
                if local_mode:
                    logger.debug("[HALT_FLAG] LOCAL_MODE enabled - skipping DynamoDB, using RDS fallback")
                    raise ValueError("LOCAL_MODE enabled - forcing RDS fallback")

                # Check if AWS credentials available - skip DynamoDB if not configured (local dev)
                if not os.environ.get("AWS_ACCESS_KEY_ID"):
                    logger.debug("[HALT_FLAG] AWS credentials not configured - skipping DynamoDB, using RDS fallback")
                    raise ValueError("AWS credentials missing - forcing RDS fallback")

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
                    RetryPolicy={"MaxAttempts": 1},  # Don't retry at boto3 level, we'll do it here
                )
                logger.info(
                    f"[HALT_FLAG_CLEARED] {reason or 'Phase 1 verified: data is fresh, resuming normal trading'}"
                )
                return True
            except Exception as e:
                last_error = e
                logger.debug(
                    f"[HALT_FLAG] DynamoDB clear attempt {attempt + 1}/{max_retries} failed: {e}. Will try RDS fallback."
                )

                # Try RDS fallback
                try:
                    rds_result = self._clear_halt_flag_rds(reason)
                    if not rds_result:
                        last_error = RuntimeError("RDS returned False (write failed)")
                        logger.warning(f"[HALT_FLAG] RDS fallback returned False (attempt {attempt + 1})")
                        if attempt < max_retries - 1:
                            import time

                            time.sleep(0.5)  # Brief backoff before retry
                            continue
                        else:
                            break
                    return rds_result  # Return True on success
                except Exception as rds_err:
                    logger.warning(f"[HALT_FLAG] RDS fallback exception (attempt {attempt + 1}): {rds_err}")
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
        error_msg = (
            f"[GOVERNANCE VIOLATION] Halt flag could not be cleared. "
            f"Both DynamoDB and RDS failed. Last error: {last_error}. "
            "This is a critical safety failure - cannot proceed with trading when halt flag unavailable. "
            "Check: (1) RDS connectivity (localhost:5432), (2) AWS credentials/DynamoDB, (3) network."
        )
        raise RuntimeError(error_msg)

    def _clear_halt_flag_rds(self, reason: str) -> bool:
        """Clear halt flag in RDS. Returns True if successfully cleared.

        RACE CONDITION FIX: Use advisory lock to serialize halt flag updates across
        concurrent orchestrator instances. Ensures clear operation is atomic.
        """
        try:
            with DatabaseContext("write") as cur:
                # Use advisory lock to serialize access to halt flag
                lock_id = self.HALT_FLAG_LOCK_ID

                try:
                    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))

                    import json

                    now_utc = datetime.now(timezone.utc)
                    msg = reason or "Phase 1 verified: data is fresh, resuming normal trading"
                    # CRITICAL FIX: this previously left halt_triggered_at and state_value (the
                    # raw crash/halt detail JSON written by _set_halt_flag_rds) untouched on
                    # clear - only halt_flag/halt_reason/halt_count were reset. Anyone inspecting
                    # algo_runtime_state after a halt cleared (this session included, mid-audit)
                    # would see a stale halt_triggered_at timestamp and a stale state_value crash
                    # reason from the LAST halt, indistinguishable from an active/recent one
                    # without separately checking halt_flag==False first. Clear all three
                    # halt-detail fields together so a cleared halt reads as cleared everywhere.
                    cur.execute(
                        """
                        UPDATE algo_runtime_state
                        SET halt_flag = FALSE, halt_count = 0, halt_reason = %s,
                            halt_triggered_at = NULL, state_value = %s, last_updated_at = %s
                        WHERE state_key = %s
                        """,
                        (
                            reason or "Phase 1 verified: data is fresh",
                            json.dumps({"halt_triggered_by": None, "reason": None, "cleared_at": now_utc.isoformat()}),
                            now_utc,
                            self.HALT_FLAG_DYNAMODB_KEY,
                        ),
                    )
                    logger.info(f"[HALT_FLAG_CLEARED] {msg} (via RDS fallback)")
                    return True
                finally:
                    try:
                        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    except Exception as unlock_err:
                        logger.warning(f"[HALT_FLAG] Could not release advisory lock: {unlock_err}")

        except Exception as e:
            logger.error(f"[HALT_FLAG] Failed to clear halt flag in RDS: {e}")
            return False
