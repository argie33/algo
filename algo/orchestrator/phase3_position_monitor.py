#!/usr/bin/env python3

import logging
import traceback
from collections.abc import Callable
from datetime import date as _date
from typing import Any

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
    log_phase_result_fn: Callable,
) -> PhaseResult:
    """Execute Phase 3: Position Monitor.

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
        PhaseResult with status 'ok', data containing position recommendations
    """
    try:
        from algo.infrastructure import MarketEventHandler
        from algo.monitoring import PositionMonitor

        monitor = PositionMonitor(config)

        try:
            meh = MarketEventHandler(config)
            try:
                open_positions = monitor.get_open_positions()
            except RuntimeError as pos_e:
                error = PhaseError(
                    category=ErrorCategory.DEPENDENCY_FAILED,
                    message="Cannot fetch open positions for halt checking",
                    root_cause=str(pos_e)[:150],
                    recoverable=False,
                    log_level="critical",
                )
                log_phase_error(3, error, log_phase_result_fn)
                raise
            halts_found = []
            for pos in open_positions:
                if "symbol" not in pos and "name" not in pos:
                    raise RuntimeError(
                        "[PHASE 3] Position missing both symbol and name. "
                        "At least one identifier is required. "
                        "Verify PositionMonitor.get_open_positions() returns valid position data."
                    )
                symbol: str = pos.get("symbol") or pos.get("name") or ""
                if not symbol:
                    raise RuntimeError("[PHASE 3] Position symbol/name is empty after fallback check")
                halt_check = meh.check_single_stock_halt(symbol)
                if halt_check and halt_check.get("halted"):
                    halts_found.append(symbol)
                    if verbose:
                        logger.warning(f"  [WARN] {symbol} halted — pending orders cancelled")
            if halts_found:
                log_phase_result_fn(
                    3,
                    "single_stock_halts",
                    "warn",
                    f"{len(halts_found)} symbols halted: {', '.join(halts_found)}",
                )
        except (OSError, RuntimeError, ValueError) as e:
            error = PhaseError(
                category=ErrorCategory.DEPENDENCY_FAILED,
                message="Halt check failed for open positions",
                root_cause=str(e)[:150],
                recoverable=True,
                log_level="warning",
            )
            log_phase_error(3, error, log_phase_result_fn)

        stale_result = monitor.check_stale_orders(run_date)
        if stale_result and stale_result.get("status") == "STALE_ORDERS_FOUND":
            if "count" not in stale_result:
                raise RuntimeError(
                    f"Stale order check returned incomplete data: missing 'count' field. "
                    f"Got keys: {list(stale_result.keys())}"
                )
            stale_count = stale_result["count"]
            alerts.send_position_alert(
                "STALE_ORDERS",
                "STALE_ORDER_ALERT",
                f"{stale_count} orders pending >1 hour",
                {"orders": stale_count},
            )

        recommendations = monitor.review_positions(run_date)

        n_raise_stop = sum(1 for r in recommendations if r["action"] == "RAISE_STOP")
        n_early_exit = sum(1 for r in recommendations if r["action"] == "EARLY_EXIT")
        n_hold = sum(1 for r in recommendations if r["action"] == "HOLD")
        n_failed = sum(1 for r in recommendations if r["action"] == "FAILED_VALIDATION")

        summary = f"{len(recommendations)} positions reviewed"
        if n_hold > 0:
            summary += f"; {n_hold} hold"
        if n_raise_stop > 0:
            summary += f", {n_raise_stop} raise-stop"
        if n_early_exit > 0:
            summary += f", {n_early_exit} early-exit"
        if n_failed > 0:
            summary += f", {n_failed} FAILED_VALIDATION"

        log_phase_result_fn(
            3,
            "position_monitor",
            "success",
            summary,
        )
        return PhaseResult(
            3,
            "position_monitor",
            "ok",
            {"recommendations": recommendations, "count": len(recommendations)},
            False,
            None,
        )

    except Exception as e:
        error = PhaseError(
            category=ErrorCategory.DEPENDENCY_FAILED,
            message="Position monitor failed unexpectedly",
            root_cause=str(e)[:200],
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(3, error, log_phase_result_fn)
        traceback.print_exc()
        return PhaseResult(3, "position_monitor", "degraded", {"recommendations": []}, False, str(e))
