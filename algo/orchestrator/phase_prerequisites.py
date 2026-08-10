#!/usr/bin/env python3
"""Common phase prerequisite checks and validation helpers.

Eliminates duplication of halt flags, dependency validation, and error handling
patterns that appear in every phase executor. Each phase can call these helpers
to check prerequisites before running core logic.
"""

import logging
from collections.abc import Callable
from typing import Any

from algo.orchestrator.phase_result import PhaseResult
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


def check_halt_flag(
    phase_num: int,
    phase_name: str,
    check_halt_flag: Callable[..., bool] | None,
    log_phase_result_fn: Callable[..., Any],
    default_output: dict[str, Any] | None = None,
) -> PhaseResult | None:
    """Check if orchestrator halt flag is set; return error PhaseResult if so.

    This helper eliminates duplicate halt-check logic across all phases:
    1. Check if halt flag is set
    2. Fetch halt reason from database
    3. Log error
    4. Return early-exit PhaseResult

    Args:
        phase_num: Phase number (1-9)
        phase_name: Phase name (e.g., "signal_generation")
        check_halt_flag: Callable that returns True if halt flag set
        log_phase_result_fn: Function to log phase result
        default_output: Default output dict if none provided (e.g., {"qualified_trades": []})

    Returns:
        PhaseResult with halt status if flag is set, None if OK to proceed
    """
    if not check_halt_flag or not check_halt_flag():
        return None

    halt_reason = "unknown halt condition"
    try:
        with DatabaseContext("read") as cur:
            cur.execute("SELECT halt_reason FROM algo_runtime_state WHERE state_key = 'orchestrator_halt'")
            result = cur.fetchone()
            if result and result[0]:
                halt_reason = result[0]
    except Exception as diagnostic_err:
        logger.debug(f"[PHASE {phase_num}] Could not fetch halt reason for diagnostics: {diagnostic_err}")

    logger.critical(f"[PHASE {phase_num}] Halt flag detected (reason: {halt_reason[:100]}). Halting execution.")
    log_phase_result_fn(phase_num, phase_name, "halt", f"Halt flag set: {halt_reason[:150]}")

    return PhaseResult(
        phase_num,
        phase_name,
        "halted",
        default_output or {},
        True,
        f"Halt flag set: {halt_reason}",
    )


def validate_phase_config(config: dict[str, Any], required_keys: list[str]) -> PhaseResult | None:
    """Validate required config keys exist before phase execution.

    Args:
        config: Configuration dictionary
        required_keys: List of required keys

    Returns:
        PhaseResult with error if validation fails, None if OK to proceed

    Example:
        result = validate_phase_config(config, ["execution_mode", "alpaca_paper_trading"])
        if result:
            return result  # Early return on config error
    """
    missing_keys = [k for k in required_keys if k not in config]
    if not missing_keys:
        return None

    error_msg = f"Configuration missing required keys: {', '.join(missing_keys)}. Check algo_config table."
    logger.error(error_msg)
    return PhaseResult(
        0,  # Generic phase number
        "config_validation",
        "error",
        {},
        False,
        error_msg,
    )
