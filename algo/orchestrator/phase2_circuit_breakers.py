#!/usr/bin/env python3

import logging
import traceback
from datetime import date as _date
from typing import Any, Callable

from algo.reporting import MetricsPublisher, AlertManager
from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)

def run(
    config: Any,
    run_date: _date,
    dry_run: bool,
    alerts: AlertManager,
    verbose: bool,
    log_phase_result_fn: Callable,
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
                for name, state in result.get("checks", {}).items():
                    _m.put_circuit_breaker(name, bool(state.get("halted")))
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")

        try:
            from algo.infrastructure import MarketEventHandler

            meh = MarketEventHandler(config)
            cb_result = meh.check_market_circuit_breaker()
            if cb_result:  # If not None, market circuit breaker triggered
                halt_level = cb_result.get("level", "?")
                halt_reason = cb_result.get(
                    "description", "market circuit breaker triggered"
                )
                if verbose:
                    logger.info(
                        f"  [HALT] circuit_breaker_L{halt_level:>1s}: {halt_reason}"
                    )
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
                return PhaseResult(
                    2, "market_circuit_breaker", "halted", {}, True, halt_reason
                )
        except Exception as e:
            log_phase_result_fn(
                2, "market_circuit_breaker", "warn", f"check failed: {e}"
            )

        if result["halted"]:
            halt_reasons = result.get("halt_reasons", ["unknown"])
            alerts.send_position_alert(
                "PORTFOLIO",
                "ACCOUNT_CIRCUIT_BREAKER",
                f'Account circuit breaker triggered: {"; ".join(halt_reasons)}',
                {"halt_reasons": halt_reasons},
            )
            log_phase_result_fn(
                2, "circuit_breakers", "halt", f'Halted: {"; ".join(halt_reasons)}'
            )
            return PhaseResult(
                2,
                "circuit_breakers",
                "halted",
                {},
                True,
                f'Halted: {"; ".join(halt_reasons)}',
            )

        log_phase_result_fn(2, "circuit_breakers", "success", "all clear")
        return PhaseResult(2, "circuit_breakers", "ok", {}, False, None)

    except Exception as e:
        traceback.print_exc()
        log_phase_result_fn(2, "circuit_breakers", "error", str(e))
        # Fail-closed: if the circuit breaker check itself crashes we cannot
        # determine whether trading is safe, so halt rather than proceed.
        return PhaseResult(2, "circuit_breakers", "halted", {}, True, str(e))
