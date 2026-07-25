#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
    log_phase_error,
)
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager, MetricsPublisher

logger = logging.getLogger(__name__)


def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable[..., Any],
) -> PhaseResult:
    """Execute Phase 2: Circuit Breakers.

    Args:
        config: Configuration object
        run_date: Date for this run
        dry_run: Whether running in dry-run mode
        alerts: AlertManager instance
        verbose: Whether to log verbose output
        log_phase_result_fn: Function to log phase results

    Returns:
        PhaseResult with status and data
    """
    try:
        from algo.risk import CircuitBreaker

        cb = CircuitBreaker(config)
        result = cb.check_all(run_date)

        # CRITICAL: Validate circuit breaker result structure before proceeding
        # Circuit breaker check MUST return checks dict - empty dict fallback hides failures
        if "checks" not in result:
            error_msg = (
                "[PHASE 2 CRITICAL] Circuit breaker check_all() returned result missing 'checks' field. "
                "Every circuit breaker result MUST include per-check status. "
                "Cannot proceed without knowing which (if any) checks failed."
            )
            logger.critical(error_msg)
            log_phase_error(2, PhaseError(
                category=ErrorCategory.DATA_INVALID,
                message=error_msg,
                root_cause="CircuitBreaker.check_all() did not return checks field",
                recoverable=False,
                log_level="critical",
            ), log_phase_result_fn)
            raise RuntimeError(error_msg)

        checks = result["checks"]
        if not isinstance(checks, dict):
            error_msg = (
                f"[PHASE 2 CRITICAL] Circuit breaker 'checks' must be dict, got {type(checks).__name__}. "
                "Data structure corruption detected."
            )
            logger.critical(error_msg)
            log_phase_error(2, PhaseError(
                category=ErrorCategory.DATA_INVALID,
                message=error_msg,
                root_cause=f"checks type is {type(checks).__name__}, expected dict",
                recoverable=False,
                log_level="critical",
            ), log_phase_result_fn)
            raise RuntimeError(error_msg)

        # CRITICAL FIX Session 345: Validate dict structure before chaining .get() calls
        # If checks["drawdown"] is None (not a dict), .get("value") crashes on None
        def safe_get_check_value(checks_dict: dict[str, Any], check_name: str) -> float | None:
            check_result = checks_dict.get(check_name)
            if check_result is None or not isinstance(check_result, dict):
                return None
            return check_result.get("value")

        risk_snapshot = {
            "drawdown_pct": safe_get_check_value(checks, "drawdown"),
            "daily_loss_pct": safe_get_check_value(checks, "daily_loss"),
            "vix_level": safe_get_check_value(checks, "vix_spike"),
            "any_triggered": result.get("halted", False),
        }

        if verbose:
            for name, state in result["checks"].items():
                flag = "[HALT]" if state.get("halted") else "[OK]  "
                label = state.get("label", name)
                logger.info(f"  {flag} {label:40s}: {state.get('reason', '')}")

        # Publish per-breaker CloudWatch metrics (non-blocking)
        try:
            with MetricsPublisher(dry_run=dry_run) as _m:
                if "checks" not in result:
                    raise RuntimeError("Circuit breaker check failed: 'checks' field missing from result")
                checks = result["checks"]
                if not isinstance(checks, dict):
                    raise RuntimeError(
                        f"Circuit breaker check failed: 'checks' must be dict, got {type(checks).__name__}"
                    )
                for name, state in checks.items():
                    _m.put_circuit_breaker(name, bool(state.get("halted")))
        except (OSError, RuntimeError) as e:
            logger.error(f"Metrics publishing failed (non-critical): {e}")

        try:
            from algo.infrastructure import MarketEventHandler

            meh = MarketEventHandler(config)
            cb_result = meh.check_market_circuit_breaker()
            if cb_result and "error" in cb_result:
                # CRITICAL: Market circuit breaker API failure must halt trading per GOVERNANCE.
                # Exception: In paper mode with credential errors, log warning and continue (dev convenience)
                error_msg = cb_result.get("description", cb_result.get("reason", "unknown"))
                error_reason = cb_result.get("reason", "")
                is_credential_error = "credential" in error_reason.lower() or "401" in error_msg.lower()
                is_transient_error = "timeout" in error_reason.lower() or "connection" in error_reason.lower()
                execution_mode = config.get("execution_mode", "paper")

                if is_credential_error and execution_mode == "paper":
                    logger.warning(
                        f"[PHASE 2] Market circuit breaker check skipped in paper mode (credentials unavailable). "
                        f"Production trading requires valid Alpaca credentials. Error: {error_msg}"
                    )
                    log_phase_result_fn(
                        2, "circuit_breakers", "ok_with_warning", "market check skipped (paper mode, creds unavailable)"
                    )
                    # Continue without circuit breaker check in paper mode - explicitly skip market check
                    cb_result = None  # Skip market circuit breaker processing below
                elif is_transient_error:
                    # Transient network errors (timeout, connection refused) are temporary
                    # Log warning and continue - if market is truly down, other phases will detect it
                    logger.warning(
                        f"[PHASE 2] Transient network error checking circuit breaker (will retry next run): {error_msg}. "
                        f"Continuing with trading - if market is down, other data quality checks will catch it."
                    )
                    log_phase_result_fn(
                        2, "circuit_breakers", "ok_with_warning", "transient network error, proceeding with caution"
                    )
                    # Continue without circuit breaker check on transient failure - explicitly skip market check
                    cb_result = None  # Skip market circuit breaker processing below
                else:
                    raise RuntimeError(
                        f"[PHASE 2 CRITICAL] Market circuit breaker API check failed: {error_msg}. "
                        f"Cannot proceed with trading without market health assessment. "
                        f"Check MarketEventHandler API connectivity and data availability."
                    )
            elif cb_result and "error" not in cb_result:
                halt_level = cb_result.get("level", "?")
                halt_reason = cb_result.get("description", "market circuit breaker triggered")
                if verbose:
                    logger.info(f"  [HALT] circuit_breaker_L{halt_level:>1s}: {halt_reason}")
                alerts.send_position_alert(
                    "PORTFOLIO",
                    "MARKET_CIRCUIT_BREAKER",
                    f"Market circuit breaker L{halt_level} triggered: {halt_reason}",
                    {
                        "level": halt_level,
                        "reason": halt_reason,
                        "pct_down": cb_result.get("pct_down"),
                    },
                )
                logger.critical(
                    f"[PHASE 2] MARKET CIRCUIT BREAKER L{halt_level} ACTIVE - Trading halted: {halt_reason}"
                )
                log_phase_result_fn(
                    2,
                    "market_circuit_breaker",
                    "halt",
                    f"L{halt_level} breaker active: {halt_reason}",
                )
                return PhaseResult(
                    2,
                    "circuit_breakers",
                    "halted",
                    risk_snapshot,
                    True,
                    f"Market circuit breaker L{halt_level}: {halt_reason}",
                )
        except (OSError, RuntimeError, ValueError) as e:
            error_msg = (
                f"[PHASE 2 CRITICAL] Market circuit breaker check failed: {e}. "
                f"Cannot proceed with trading without market health assessment. "
                f"Market circuit breaker API failure must halt trading per GOVERNANCE (fail-fast on missing data). "
                f"Check MarketEventHandler API connectivity and data availability."
            )
            logger.critical(error_msg)
            error = PhaseError(
                category=ErrorCategory.DEPENDENCY_FAILED,
                message=error_msg,
                root_cause=str(e)[:150],
                recoverable=False,
                log_level="critical",
            )
            log_phase_error(2, error, log_phase_result_fn)
            raise RuntimeError(error_msg) from e

        if result["halted"]:
            # GOVERNANCE: Fail-fast on data contract violations. If halted=True, halt_reasons MUST be present.
            if "halt_reasons" not in result:
                error = PhaseError(
                    category=ErrorCategory.DATA_INVALID,
                    message="Circuit breaker halt triggered but halt_reasons missing from result",
                    root_cause="Data contract violation: halted=True requires halt_reasons list",
                    recoverable=False,
                    log_level="error",
                )
                log_phase_error(2, error, log_phase_result_fn)
                return PhaseResult(
                    2,
                    "circuit_breakers",
                    "halted",
                    risk_snapshot,
                    True,
                    "Circuit breaker halt: halt_reasons missing (data contract violation)",
                )
            halt_reasons = result["halt_reasons"]
            if not isinstance(halt_reasons, list):
                logger.error(
                    f"CRITICAL: Circuit breaker halt_reasons has invalid type {type(halt_reasons)}, expected list: {halt_reasons}"
                )
                raise ValueError(f"Circuit breaker halt_reasons must be a list, got {type(halt_reasons)}")
            if len(halt_reasons) == 0:
                logger.error(
                    "CRITICAL: Circuit breaker triggered (halt=True) but halt_reasons list is empty. "
                    "Cannot determine halt reason. This indicates incomplete data from Phase 2."
                )
                raise ValueError("Circuit breaker halt triggered with no halt_reasons specified")
            alerts.send_position_alert(
                "PORTFOLIO",
                "ACCOUNT_CIRCUIT_BREAKER",
                f"Account circuit breaker triggered: {'; '.join(halt_reasons)}",
                {"halt_reasons": halt_reasons},
            )
            log_phase_result_fn(2, "circuit_breakers", "halt", f"Halted: {'; '.join(halt_reasons)}")
            return PhaseResult(
                2,
                "circuit_breakers",
                "halted",
                risk_snapshot,
                True,
                f"Halted: {'; '.join(halt_reasons)}",
            )

        log_phase_result_fn(2, "circuit_breakers", "success", "all clear")
        phase_data = {**risk_snapshot, "status": "ok", "reason": "all circuit breaker checks passed"}
        validate_phase_data(2, phase_data)
        return PhaseResult(
            2,
            "circuit_breakers",
            "ok",
            phase_data,
            False,
            None,
        )

    except Exception as e:
        error = PhaseError(
            category=ErrorCategory.DEPENDENCY_FAILED,
            message="Circuit breaker check failed unexpectedly",
            root_cause=str(e)[:200],
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(2, error, log_phase_result_fn)
        logger.critical(f"[PHASE 2] Circuit breaker check failed: {str(e)[:100]}")
        log_phase_result_fn(2, "circuit_breakers", "halt", f"Check failed: {str(e)[:50]}")
        return PhaseResult(
            2,
            "circuit_breakers",
            "halted",
            {"status": "halted", "reason": f"Circuit breaker check failed: {str(e)[:80]}"},
            True,
            f"Circuit breaker check failed: {str(e)[:80]}",
        )
