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
    """Execute Phase 3a: Position Reconciliation.

    Delegates to DailyReconciliation (consolidated from PositionReconciler).
    Phase 3a is a lightweight check; comprehensive reconciliation is in Phase 7.

    Args:
        config: Configuration object
        get_conn: Function to get database connection
        put_conn: Function to return database connection
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status 'ok' (fail-open)
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
                "3a",
                "reconciliation",
                "success",
                f"{positions_count} positions verified",
            )
        elif "unavailable" in error_msg.lower() or "401" in error_msg or "unauthorized" in error_msg.lower():
            # Alpaca 401 on weekends/outside market hours is expected — treat as skip, not alert
            log_phase_result_fn(
                "3a",
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
                "3a",
                "reconciliation",
                "alert",
                reason,
            )

        return PhaseResult("3a", "reconciliation", "ok", result, False, None)

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error = PhaseError(
            category=ErrorCategory.DATABASE_ERROR,
            message="Position reconciliation database error",
            root_cause=str(e)[:200],
            recoverable=True,
            log_level="error",
        )
        log_phase_error("3a", error, log_phase_result_fn)
        traceback.print_exc()
        return PhaseResult("3a", "reconciliation", "error", {}, False, str(e))
