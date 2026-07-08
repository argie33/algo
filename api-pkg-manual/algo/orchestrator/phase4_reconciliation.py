#!/usr/bin/env python3

import logging
import traceback
from collections.abc import Callable
from datetime import date as _date
from typing import Any

import psycopg2

from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
    log_phase_error,
)
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager

logger = logging.getLogger(__name__)


def run(
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
            if "mismatches" not in partial_fill_result:
                raise RuntimeError(
                    f"Partial fill check returned incomplete data: missing 'mismatches' field. "
                    f"Got keys: {list(partial_fill_result.keys())}"
                )
            if partial_fill_result["mismatches"] > 0:
                logger.warning(
                    f"[PHASE_3A] Detected {partial_fill_result['mismatches']} "
                    f"partial fills — corrected quantities to match Alpaca"
                )
                result["partial_fill_corrections"] = partial_fill_result

        # Validate result structure upfront
        if "success" not in result or result["success"] is None:
            raise RuntimeError(f"Reconciliation result missing 'success' field. Got keys: {list(result.keys())}")

        # CRITICAL: Explicitly extract error message; do not silently default to empty string.
        # This masks reconciliation failures and prevents debugging failed syncs.
        error_msg = result.get("reason")
        if error_msg is None:
            error_msg = result.get("error")
        if error_msg is None:
            error_msg = "(no error details provided)"

        if result["success"]:
            positions_count = result.get("positions")
            if positions_count is None:
                raise RuntimeError(
                    "Reconciliation succeeded but position count is missing. "
                    "Cannot log success without position verification count."
                )
            log_phase_result_fn(
                4,
                "reconciliation",
                "success",
                f"{positions_count} positions verified",
            )
        elif "unavailable" in error_msg.lower() or "401" in error_msg or "unauthorized" in error_msg.lower():
            # Alpaca 401 on weekends/outside market hours is expected — treat as skip, not alert
            log_phase_result_fn(
                4,
                "reconciliation",
                "success",
                f"Skipped: broker unavailable ({error_msg[:80]})",
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

        return PhaseResult(4, "reconciliation", "ok", result, False, None)

    except ValueError as e:
        # Alpaca broker unavailable (401, network error, etc.) - graceful degradation
        if "401" in str(e) or "unauthorized" in str(e).lower() or "alpaca" in str(e).lower():
            logger.warning(f"[PHASE 4] Broker unavailable: {str(e)[:100]} - returning empty reconciliation")
            log_phase_result_fn(4, "reconciliation", "success", "broker unavailable - skipping reconciliation")
            # Return success with empty data so downstream phases can proceed
            return PhaseResult(
                4, "reconciliation", "ok", {"success": False, "reason": "broker unavailable"}, False, None
            )
        raise

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error = PhaseError(
            category=ErrorCategory.DATABASE_ERROR,
            message="Position reconciliation database error",
            root_cause=str(e)[:200],
            recoverable=True,
            log_level="error",
        )
        log_phase_error(4, error, log_phase_result_fn)
        traceback.print_exc()
        return PhaseResult(4, "reconciliation", "error", {}, False, str(e))

    except Exception as e:
        # Catch any other errors (including RuntimeError) and check if broker-related
        error_str = str(e).lower()
        if "401" in str(e) or "unauthorized" in error_str or "alpaca" in error_str or "broker" in error_str:
            logger.warning(f"[PHASE 4] Broker error (non-ValueError): {str(e)[:100]} - returning empty reconciliation")
            log_phase_result_fn(4, "reconciliation", "success", "broker unavailable - skipping reconciliation")
            return PhaseResult(
                4, "reconciliation", "ok", {"success": False, "reason": "broker unavailable"}, False, None
            )
        raise
