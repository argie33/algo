#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
    log_phase_error,
)
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)


def run(  # noqa: C901
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 4: Reconciliation.

    Reconciles broker position data with database records.
    For paper trading, gracefully handles broker unavailability.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok' (succeeds even when broker unavailable)
    """
    try:
        from algo.infrastructure.reconciliation import DailyReconciliation
        from utils.db import DatabaseContext

        recon = DailyReconciliation(config)
        result = recon.run_daily_reconciliation(run_date)

        # Check for partial fills that need immediate reconciliation
        with DatabaseContext("write") as cur:
            partial_fill_result = recon.check_partial_fills(cur)

            # CRITICAL FIX: Validate partial fill result structure completely
            # Previously: only checked 'mismatches' field existed
            # Now: validate result is dict, has all required fields, has no error status
            if not isinstance(partial_fill_result, dict):
                raise RuntimeError(
                    f"[PHASE 4] Partial fill check returned invalid type {type(partial_fill_result).__name__}. "
                    f"Expected dict. API response may be corrupted."
                )

            if "mismatches" not in partial_fill_result:
                raise RuntimeError(
                    f"[PHASE 4] Partial fill check returned incomplete data: missing 'mismatches' field. "
                    f"Got keys: {list(partial_fill_result.keys())}. "
                    f"API response structure unexpected."
                )

            # Validate mismatches is numeric
            if not isinstance(partial_fill_result["mismatches"], (int, float)):
                raise RuntimeError(
                    f"[PHASE 4] 'mismatches' field is invalid type {type(partial_fill_result['mismatches']).__name__}. "
                    f"Expected int. API returned malformed data."
                )

            # Check for error in result
            if partial_fill_result.get("error"):
                error_detail = partial_fill_result.get("error")
                raise RuntimeError(
                    f"[PHASE 4] Partial fill check returned error: {error_detail}. "
                    f"Broker API may be unavailable or order state corrupted. Cannot proceed with reconciliation."
                )

            if partial_fill_result["mismatches"] > 0:
                logger.warning(
                    f"[PHASE 4] Detected {partial_fill_result['mismatches']} "
                    f"partial fills - corrected quantities to match Alpaca"
                )
                result["partial_fill_corrections"] = partial_fill_result

            # CRITICAL: auth_unavailable means the partial-fill check never actually ran
            # (broker 401'd before it could compare any orders) - the 0 mismatches above is
            # "not checked", not "checked and clean".
            if partial_fill_result.get("auth_unavailable"):
                # FAIL-FAST: Cannot validate partial fills without broker auth. This is CRITICAL
                # for accurate position tracking. Continuing with unvalidated partial fills risks
                # position state divergence and incorrect risk calculations.
                error_msg = (
                    "[PHASE 4 FAIL-FAST] Cannot validate partial fills: broker authentication unavailable. "
                    "Partial fills may exist but cannot be detected or corrected. "
                    "This is a critical safety check - reconciliation must not proceed without it. "
                    "Remedy: restore broker credentials (APCA_API_KEY_ID/APCA_API_SECRET_KEY), or "
                    "run with --dry-run to skip trading. Aborting Phase 4."
                )
                logger.critical(error_msg)
                raise RuntimeError(error_msg)

        # Validate result structure upfront
        if "success" not in result or result["success"] is None:
            raise RuntimeError(f"Reconciliation result missing 'success' field. Got keys: {list(result.keys())}")

        # CRITICAL: Result MUST have 'reason' field. Do not accept fallbacks.
        if "reason" not in result:
            raise RuntimeError(
                f"[PHASE 4 CRITICAL] Reconciliation result missing 'reason' field. "
                f"Result keys: {list(result.keys())}. Cannot determine reconciliation status without reason."
            )
        error_msg = result["reason"]

        if result["success"]:
            positions_count = result.get("positions")
            if positions_count is None:
                raise RuntimeError(
                    "Reconciliation succeeded but position count is missing. "
                    "Cannot log success without position verification count."
                )

            # Log reconciliation result to database for audit trail
            # CRITICAL: Audit trail persistence is non-negotiable per GOVERNANCE (data integrity).
            with DatabaseContext("write") as cur:
                # match_pct previously hardcoded 100.0 whenever positions_count >= 0 - true for
                # every realistic value (counts can't be negative), so this was effectively a
                # constant "100% match" written to algo_reconciliation_log on every successful
                # run, regardless of actual reconciliation quality. result["success"] only means
                # the reconciliation process completed without raising - DailyReconciliation
                # returns success=True unconditionally (see reconciliation.py lines ~576/1304)
                # even when partial-fill mismatches were detected and corrected, or when
                # broker-vs-DB position value drift exceeded 1% (drift_pct check, log-only,
                # never flips success to False). The mismatches count from check_partial_fills
                # above (already used for errors_found below) was sitting right here unused.
                # This audit table exists specifically so an operator can see reconciliation
                # health over time - a constant 100% defeats that purpose.
                if "mismatches" not in partial_fill_result:
                    raise RuntimeError(
                        f"[PHASE 4 CRITICAL] partial_fill_result missing 'mismatches' key. "
                        f"Result structure: {partial_fill_result}. "
                        f"Cannot calculate reconciliation match_pct without mismatch count. "
                        f"Check DailyReconciliation.check_partial_fills() return value."
                    )
                mismatches_count = partial_fill_result["mismatches"]
                if not isinstance(mismatches_count, int) or mismatches_count < 0:
                    raise RuntimeError(
                        f"[PHASE 4 CRITICAL] partial_fill_result['mismatches'] invalid: {mismatches_count!r}. "
                        f"Expected non-negative int. Cannot calculate reconciliation match_pct."
                    )

                # CRITICAL FIX: Session 345 - If auth was unavailable, reconciliation didn't actually run.
                # Don't record 100% match when check was skipped. Use NULL to indicate check was skipped.
                if "auth_unavailable" not in partial_fill_result:
                    raise RuntimeError(
                        "[PHASE 4] CRITICAL: partial_fill_result missing required 'auth_unavailable' field. "
                        "Cannot determine if broker authentication was available for reconciliation. "
                        "Check_partial_fills() must always return this field."
                    )
                auth_unavailable = partial_fill_result["auth_unavailable"]
                if auth_unavailable:
                    match_pct = None  # NULL to indicate check was not performed
                    logger.info("[PHASE 4] Recording NULL match_pct in audit (auth unavailable, check skipped)")
                elif positions_count > 0:
                    match_pct = max(0.0, 100.0 * (1 - (mismatches_count / positions_count)))
                else:
                    match_pct = 100.0  # No positions to reconcile - vacuously fully matched

                try:
                    cur.execute(
                        """INSERT INTO algo_reconciliation_log
                           (reconciliation_date, match_percentage, sync_count, created_at)
                           VALUES (%s, %s, %s, NOW())""",
                        (run_date, match_pct, positions_count),
                    )
                except psycopg2.DatabaseError as db_err:
                    error_msg = (
                        f"[PHASE 4 CRITICAL] Failed to persist reconciliation result to audit log: {db_err}. "
                        f"Cannot proceed with reconciliation when audit trail is unavailable. "
                        f"Database may be corrupted or inaccessible. Check database connectivity and disk space."
                    )
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg) from db_err

            summary = f"{positions_count} positions verified"
            if result.get("partial_fill_check_skipped"):
                summary += " (partial-fill check skipped: broker auth unavailable)"
            # CRITICAL: reconciliation.py's own post-commit verification can genuinely detect
            # the portfolio snapshot didn't persist as expected - don't let that surface only as
            # a log line nobody watching the orchestrator would see. Not escalated to "alert"
            # status (the write itself succeeded; this is "we couldn't confirm it", not "it
            # failed"), but it must not be silently absorbed into an unqualified "success" either.
            if result.get("final_verification_failed"):
                if "final_verification_detail" not in result:
                    raise RuntimeError(
                        "[PHASE 4] CRITICAL: final_verification_failed=True but final_verification_detail is missing. "
                        "Must provide explicit error reason when verification fails. "
                        "Check reconciliation.py::run_daily_reconciliation()."
                    )
                detail = result["final_verification_detail"]
                summary += f" (WARNING: final verification failed - {detail})"
                logger.warning(f"[PHASE 4] Portfolio snapshot final verification failed: {detail}")
            log_phase_result_fn(
                4,
                "reconciliation",
                "success",
                summary,
            )
            # sync_count/avg_match_pct/errors_found: the health dashboard
            # (dashboard/panels/health.py, Phase 4 detail row) reads these exact keys, but
            # `result` never carried them - previously always rendered nothing despite
            # positions_count/match_pct being computed right above for the audit-log INSERT.
            result["sync_count"] = positions_count
            result["avg_match_pct"] = match_pct
            result["errors_found"] = mismatches_count
            validate_phase_data(4, result)
            return PhaseResult(4, "reconciliation", "ok", result, False, None)
        else:
            # Reconciliation failed - return error status with appropriate logging
            if "unavailable" in error_msg.lower() or "401" in error_msg or "unauthorized" in error_msg.lower():
                # Broker authentication/availability error during market hours = critical failure
                # Only gracefully skip on weekends/market-closed, otherwise fail-fast
                logger.error(f"[PHASE 4] CRITICAL: Broker authentication/availability error: {error_msg[:120]}")
                log_phase_result_fn(
                    4,
                    "reconciliation",
                    "alert",
                    f"Broker unavailable ({error_msg[:100]}). Positions cannot be reconciled. Check Alpaca API status.",
                )
            else:
                # CRITICAL: Always use explicit error message, don't default to generic
                if not error_msg:
                    logger.error("[RECONCILIATION] Error message missing - data quality issue")
                    reason = "reconciliation failed (error message missing)"
                else:
                    reason = error_msg
                log_phase_result_fn(
                    4,
                    "reconciliation",
                    "alert",
                    reason,
                )
            return PhaseResult(4, "reconciliation", "error", result, False, error_msg)

    except ValueError as e:
        # Broker or API error - fail-fast to prevent trading on stale position data
        error_str = str(e).lower()
        if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str:
            logger.error(f"[PHASE 4] CRITICAL: Broker authentication failed: {str(e)[:120]}")
            error_msg = f"Broker authentication error: {str(e)[:200]}"
        else:
            logger.error(f"[PHASE 4] CRITICAL: Reconciliation ValueError: {str(e)[:120]}")
            error_msg = f"Reconciliation error: {str(e)[:200]}"

        log_phase_result_fn(4, "reconciliation", "alert", error_msg)
        return PhaseResult(4, "reconciliation", "error", {"success": False, "reason": error_msg}, False, error_msg)

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error = PhaseError(
            category=ErrorCategory.DATABASE_ERROR,
            message="Position reconciliation database error",
            root_cause=str(e)[:200],
            recoverable=True,
            log_level="error",
        )
        log_phase_error(4, error, log_phase_result_fn)
        return PhaseResult(4, "reconciliation", "error", {"success": False, "reason": str(e)[:200]}, False, str(e))

    except Exception as e:
        # All reconciliation errors are critical - fail-fast to prevent stale data trading
        error_str = str(e).lower()
        logger.error(f"[PHASE 4] CRITICAL: Reconciliation failed: {type(e).__name__}: {str(e)[:120]}")

        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        log_phase_result_fn(4, "reconciliation", "alert", error_msg)
        return PhaseResult(4, "reconciliation", "error", {"success": False, "reason": error_msg}, False, error_msg)
