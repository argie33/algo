#!/usr/bin/env python3

import logging
from collections.abc import Callable
from datetime import date as _date
from typing import Any

from algo.orchestrator.config_validator import validate_phase_config
from algo.orchestrator.phase_data_contract import validate_phase_data
from algo.orchestrator.phase_error_handling import (
    ErrorCategory,
    PhaseError,
    log_phase_error,
)
from algo.orchestrator.phase_result import PhaseResult
from algo.reporting import AlertManager, MetricsPublisher

logger = logging.getLogger(__name__)


def run(  # noqa: C901
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
    validate_phase_config(config, "phase_2_circuit_breakers")

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
            log_phase_error(
                2,
                PhaseError(
                    category=ErrorCategory.DATA_INVALID,
                    message=error_msg,
                    root_cause="CircuitBreaker.check_all() did not return checks field",
                    recoverable=False,
                    log_level="critical",
                ),
                log_phase_result_fn,
            )
            raise RuntimeError(error_msg)

        checks = result["checks"]
        if not isinstance(checks, dict):
            error_msg = (
                f"[PHASE 2 CRITICAL] Circuit breaker 'checks' must be dict, got {type(checks).__name__}. "
                "Data structure corruption detected."
            )
            logger.critical(error_msg)
            log_phase_error(
                2,
                PhaseError(
                    category=ErrorCategory.DATA_INVALID,
                    message=error_msg,
                    root_cause=f"checks type is {type(checks).__name__}, expected dict",
                    recoverable=False,
                    log_level="critical",
                ),
                log_phase_result_fn,
            )
            raise RuntimeError(error_msg)

        # CRITICAL: Validate circuit breaker checks dict is NOT EMPTY
        # If checks={}, no circuit breaker is evaluated and trading proceeds unguarded
        if not checks:
            error_msg = (
                "[PHASE 2 CRITICAL] Circuit breaker checks returned empty dict. "
                "This means CircuitBreaker.check_all() failed to populate any checks. "
                "Cannot proceed without circuit breaker enforcement - halt trading to prevent unguarded execution."
            )
            logger.critical(error_msg)
            log_phase_error(
                2,
                PhaseError(
                    category=ErrorCategory.DATA_INVALID,
                    message=error_msg,
                    root_cause="CircuitBreaker.check_all() returned empty checks dict",
                    recoverable=False,
                    log_level="critical",
                ),
                log_phase_result_fn,
            )
            raise RuntimeError(error_msg)

        # CRITICAL: Validate each check is a dict with a 'value' field
        def extract_check_value(check_result: Any) -> float | None:
            """Extract value from check result dict, or None if missing."""
            return check_result.get("value") if isinstance(check_result, dict) else None

        risk_snapshot = {
            "drawdown_pct": extract_check_value(checks.get("drawdown")),
            "daily_loss_pct": extract_check_value(checks.get("daily_loss")),
            "vix_level": extract_check_value(checks.get("vix_spike")),
            "any_triggered": result["halted"],
        }

        if verbose:
            for name, state in result["checks"].items():
                flag = "[HALT]" if state["halted"] else "[OK]  "
                label = state.get("label", name)
                logger.info(f"  {flag} {label:40s}: {state['reason']}")

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
                    _m.put_circuit_breaker(name, bool(state["halted"]))
        except (OSError, RuntimeError) as e:
            logger.error(f"Metrics publishing failed (non-critical): {e}")

        try:
            from algo.infrastructure import MarketEventHandler

            meh = MarketEventHandler(config)
            cb_result = meh.check_market_circuit_breaker()
            if cb_result and "error" in cb_result:
                # CRITICAL: Market circuit breaker API failure must halt trading per GOVERNANCE.
                # Exception: In paper mode with credential errors, log warning and continue (dev convenience)
                error_reason = cb_result.get("reason")
                if error_reason is None:
                    error_reason = cb_result.get("description")
                if error_reason is None:
                    raise RuntimeError(
                        f"[PHASE 2 CRITICAL] Market circuit breaker error response missing both 'reason' and 'description' fields. "
                        f"Response keys: {list(cb_result.keys())}. Data integrity issue. "
                        f"Cannot determine error severity."
                    )
                error_msg = error_reason
                is_credential_error = "credential" in error_reason.lower() or "401" in error_msg.lower()
                is_transient_error = "timeout" in error_reason.lower() or "connection" in error_reason.lower()
                is_data_validation_error = "data_validation" in error_reason.lower() or "validation" in error_reason.lower()
                execution_mode = config.get("execution_mode")
                if execution_mode is None:
                    raise ValueError(
                        "[PHASE 2 CRITICAL] execution_mode config missing. "
                        "Cannot determine trading mode (live vs paper). "
                        "Set explicit execution_mode in algo_config table."
                    )

                if (is_credential_error or is_data_validation_error) and execution_mode == "paper":
                    logger.warning(
                        f"[PHASE 2] Market circuit breaker check skipped in paper mode (API error or incomplete data). "
                        f"Production trading requires valid market data access. Error: {error_msg}"
                    )
                    log_phase_result_fn(
                        2, "circuit_breakers", "ok_with_warning", "market check skipped (paper mode, creds unavailable)"
                    )
                    # Continue without circuit breaker check in paper mode - explicitly skip market check
                    cb_result = None  # Skip market circuit breaker processing below
                elif is_credential_error and execution_mode != "paper":
                    # Live/review mode requires working circuit breaker check
                    msg = (
                        f"[PHASE 2 CRITICAL] Credential error checking market circuit breaker in {execution_mode} mode: {error_msg}. "
                        f"Live/review modes require valid Alpaca credentials and working circuit breaker. "
                        f"Cannot proceed with trading."
                    )
                    logger.critical(msg)
                    log_phase_result_fn(2, "circuit_breakers", "halt", msg)
                    raise RuntimeError(msg)
                elif is_transient_error:
                    # CRITICAL FIX: Transient network errors cannot be silently ignored for market circuit breaker.
                    # Circuit breaker is a critical safety gate - cannot proceed without verification.
                    # Transient errors may hide real market issues (circuit breaker service down, network split, etc.)
                    msg = (
                        f"[PHASE 2 CRITICAL] Transient network error checking market circuit breaker: {error_msg}. "
                        f"Cannot proceed with trading without verified market health status. "
                        f"Circuit breaker is a critical safety gate - transient errors must be escalated, not silently skipped. "
                        f"Retry after verifying network connectivity and market data API availability."
                    )
                    logger.critical(msg)
                    log_phase_result_fn(2, "circuit_breakers", "halt", msg)
                    raise RuntimeError(msg)
                else:
                    raise RuntimeError(
                        f"[PHASE 2 CRITICAL] Market circuit breaker API check failed: {error_msg}. "
                        f"Cannot proceed with trading without market health assessment. "
                        f"Check MarketEventHandler API connectivity and data availability."
                    )
            elif cb_result and "error" not in cb_result:
                halt_level = cb_result["level"]
                halt_reason = cb_result["description"]
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

        # Alpaca account-freeze / PDT-restriction check. Gated on execution_mode=="auto" (the
        # only mode that actually submits real orders to this broker account - see
        # reconciliation.py's identical gate) so this is a no-op for local/paper/dry-run
        # development and only engages once real money is on the line. Without this, an
        # account Alpaca has frozen (PDT violation, compliance hold, negative balance, etc.)
        # gives zero proactive signal - every subsequent entry would just fail with a generic
        # per-symbol 403 from order_manager.py, indistinguishable from an ordinary rejection,
        # with nothing pointing at the real account-level cause. Same-day stop-loss exits are
        # intentional (see exit_engine.py's hard-stop-overrides-min_hold_days comment), so this
        # system can and does generate day trades - a real PDT flag is a live concern here, not
        # a hypothetical one.
        execution_mode = config.get("execution_mode")
        if execution_mode == "auto":
            try:
                from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter

                account_data = AlpacaBrokerAdapter(config).fetch_account()
                # CRITICAL FIX: Fail-fast if account status fields are missing.
                # These are safety-critical flags - missing data means API is broken or incomplete.
                # Silent fallback to False could allow trading on a frozen account.
                if "trading_blocked" not in account_data:
                    raise KeyError(
                        "[PHASE 2 CRITICAL] Account data missing required 'trading_blocked' field. "
                        "Cannot verify account is not frozen before submitting live orders. "
                        "Check Alpaca API response."
                    )
                if "account_blocked" not in account_data:
                    raise KeyError(
                        "[PHASE 2 CRITICAL] Account data missing required 'account_blocked' field. "
                        "Cannot verify account is not blocked before submitting live orders. "
                        "Check Alpaca API response."
                    )
                trading_blocked = bool(account_data["trading_blocked"])
                account_blocked = bool(account_data["account_blocked"])
                if trading_blocked or account_blocked:
                    reason = (
                        f"Alpaca account frozen (trading_blocked={trading_blocked}, "
                        f"account_blocked={account_blocked}) - broker has stopped "
                        "all trading on this account (PDT violation, compliance hold, negative "
                        "balance, etc). No orders can be submitted until resolved directly with Alpaca."
                    )
                    logger.critical(f"[PHASE 2] ACCOUNT BLOCKED: {reason}")
                    alerts.send_position_alert(
                        "PORTFOLIO",
                        "ACCOUNT_BLOCKED",
                        reason,
                        {
                            "trading_blocked": trading_blocked,
                            "account_blocked": account_blocked,
                        },
                    )
                    log_phase_result_fn(2, "account_status", "halt", reason)
                    return PhaseResult(2, "circuit_breakers", "halted", risk_snapshot, True, reason)
                # CRITICAL FIX: Fail-fast if pattern_day_trader flag is missing
                if "pattern_day_trader" not in account_data:
                    raise KeyError(
                        "[PHASE 2 CRITICAL] Account data missing required 'pattern_day_trader' field. "
                        "Cannot verify PDT status before submitting live orders. "
                        "Check Alpaca API response."
                    )
                pattern_day_trader = bool(account_data["pattern_day_trader"])
                if pattern_day_trader:
                    daytrade_count = account_data.get("daytrade_count")
                    if daytrade_count is None:
                        logger.warning(
                            "[PHASE 2] Alpaca account flagged pattern_day_trader=True "
                            "but daytrade_count is missing. Cannot determine current day-trade count. "
                            "PDT limit enforcement may be inaccurate."
                        )
                    logger.warning(
                        f"[PHASE 2] Alpaca account flagged pattern_day_trader=True "
                        f"(daytrade_count={daytrade_count}). Alpaca will reject "
                        "same-day round-trip orders once the rolling 5-business-day day-trade limit "
                        "is exceeded on an account under $25k equity - a subsequent entry rejection "
                        "may be this, not a data/config bug."
                    )
            except RuntimeError as e:
                # fetch_account() raises RuntimeError specifically for missing/invalid
                # credentials. execution_mode=="auto" means real orders are about to be
                # submitted, so - unlike the paper-mode credential skip for the market circuit
                # breaker above - this must halt, not degrade: we cannot verify the account
                # isn't frozen before letting Phase 8 submit real orders into it.
                error_msg = (
                    f"[PHASE 2 CRITICAL] Cannot verify Alpaca account status before trading: {e}. "
                    "execution_mode=auto requires a verified, unblocked broker account."
                )
                logger.critical(error_msg)
                log_phase_result_fn(2, "account_status", "halt", error_msg)
                return PhaseResult(2, "circuit_breakers", "halted", risk_snapshot, True, error_msg)

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

    except (RuntimeError, ValueError, KeyError) as e:
        error = PhaseError(
            category=ErrorCategory.DEPENDENCY_FAILED,
            message="Circuit breaker check failed - data/validation error",
            root_cause=str(e)[:200],
            recoverable=False,
            log_level="critical",
        )
        log_phase_error(2, error, log_phase_result_fn)
        logger.critical(f"[PHASE 2] Circuit breaker check failed (validation error): {str(e)[:500]}")
        return PhaseResult(
            2,
            "circuit_breakers",
            "halted",
            {"status": "halted", "reason": f"Circuit breaker check failed: {str(e)[:80]}"},
            True,
            f"Circuit breaker check failed: {str(e)[:80]}",
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
        logger.critical(f"[PHASE 2] Circuit breaker check failed: {str(e)[:500]}")
        log_phase_result_fn(2, "circuit_breakers", "halt", f"Check failed: {str(e)[:50]}")
        return PhaseResult(
            2,
            "circuit_breakers",
            "halted",
            {"status": "halted", "reason": f"Circuit breaker check failed: {str(e)[:80]}"},
            True,
            f"Circuit breaker check failed: {str(e)[:80]}",
        )
