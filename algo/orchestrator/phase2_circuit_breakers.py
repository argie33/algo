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
            if cb_result:  # If not None, market circuit breaker triggered
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
                log_phase_result_fn(
                    2,
                    "market_circuit_breaker",
                    "halt",
                    f"L{halt_level} breaker active: {halt_reason}",
                )
                return PhaseResult(2, "market_circuit_breaker", "halted", {}, True, halt_reason)
        except (OSError, RuntimeError, ValueError) as e:
            error = PhaseError(
                category=ErrorCategory.DEPENDENCY_FAILED,
                message="Market circuit breaker check failed",
                root_cause=str(e)[:150],
                recoverable=True,
                log_level="warning",
            )
            log_phase_error(2, error, log_phase_result_fn)
            logger.warning(
                f"Market circuit breaker check skipped due to dependency failure: {e}. "
                f"Proceeding with account circuit breakers only."
            )

        if result["halted"]:
            halt_reasons = result.get("halt_reasons", ["unknown"])
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
                {},
                True,
                f"Halted: {'; '.join(halt_reasons)}",
            )

        log_phase_result_fn(2, "circuit_breakers", "success", "all clear")
        return PhaseResult(2, "circuit_breakers", "ok", {}, False, None)

    except Exception as e:
        error = PhaseError(
            category=ErrorCategory.DEPENDENCY_FAILED,
            message="Circuit breaker check failed unexpectedly",
            root_cause=str(e)[:200],
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(2, error, log_phase_result_fn)
        traceback.print_exc()
        # Fail-closed: if the circuit breaker check itself crashes we cannot
        # determine whether trading is safe, so halt rather than proceed.
        return PhaseResult(2, "circuit_breakers", "halted", {}, True, str(e))
