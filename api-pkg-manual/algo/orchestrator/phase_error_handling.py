#!/usr/bin/env python3
"""Standardized error handling for orchestrator phases.

Ensures consistent error reporting across all phases so operators can:
1. Distinguish between "no data" (normal) and "failed to load data" (error)
2. Identify root causes from log messages
3. Know whether to retry, escalate, or continue
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of phase failures."""

    # Data quality issues (warrant halt)
    DATA_MISSING = "data_missing"  # Required table/data doesn't exist
    DATA_STALE = "data_stale"  # Data is old, not fresh enough
    DATA_INCOMPLETE = "data_incomplete"  # Data exists but is incomplete/degraded
    DATA_INVALID = "data_invalid"  # Data exists but schema/validation failed

    # System/infrastructure issues (warrant halt)
    DATABASE_ERROR = "database_error"  # DB connection failed, timeout, etc.
    CONFIGURATION_ERROR = "configuration_error"  # Missing config, invalid config
    DEPENDENCY_FAILED = "dependency_failed"  # Required phase didn't complete

    # Policy/gate issues (warrant halt but for different reason)
    MARKET_CLOSED = "market_closed"  # Market is closed (normal, not error)
    MARKET_REGIME_HALTED = "market_regime_halted"  # Market regime gate halted entries
    EXPOSURE_POLICY_HALTED = "exposure_policy_halted"  # Exposure limits halted entries
    HALT_FLAG_SET = "halt_flag_set"  # Halt flag was set by Phase 1

    # Operational issues (may warrant retry)
    TIMEOUT = "timeout"  # Operation timed out
    RESOURCE_UNAVAILABLE = "resource_unavailable"  # Resource (lock, connection pool) unavailable

    # Transient issues (warrant retry)
    TEMPORARY_FAILURE = "temporary_failure"  # Transient error, retry may help


@dataclass
class PhaseError:
    """Structured error information from a phase.

    Allows operators to understand WHAT failed, WHY it failed, and WHAT TO DO.
    """

    category: ErrorCategory
    message: str  # Human-readable message
    root_cause: str | None = None  # Technical details for debugging
    recoverable: bool = False  # Whether retry might help
    log_level: str = "critical"  # "critical", "error", "warning"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "category": self.category.value,
            "message": self.message,
            "root_cause": self.root_cause,
            "recoverable": self.recoverable,
        }


def log_phase_error(phase_num: int | str, error: PhaseError, log_fn: Any = None) -> None:
    """Log phase error with structured information.

    Args:
        phase_num: Phase number
        error: PhaseError with category and details
        log_fn: Optional logging function (for phase result logging)
    """
    prefix = f"[PHASE {phase_num}]"

    # Log to application logger at appropriate level
    log_level = getattr(logging, error.log_level.upper(), logging.CRITICAL)
    if error.root_cause:
        logger.log(
            log_level,
            f"{prefix} {error.category.value.upper()}: {error.message}\n  Root cause: {error.root_cause}",
        )
    else:
        logger.log(log_level, f"{prefix} {error.category.value.upper()}: {error.message}")

    # Log to phase result (for operators)
    if log_fn:
        try:
            log_fn(
                phase_num,
                f"phase_{phase_num}_error",
                error.log_level if error.log_level in ("error", "halt") else "error",
                f"{error.category.value}: {error.message}",
            )
        except Exception as e:
            logger.warning(f"Could not log to phase result: {e}")


def create_error_message(category: ErrorCategory, details: str) -> str:
    """Create a standardized error message that operators can act on.

    Maps error categories to recovery guidance.
    """
    guidance = {
        ErrorCategory.DATA_MISSING: "Check that all required loaders have completed.",
        ErrorCategory.DATA_STALE: "Check loader pipeline for delays or failures.",
        ErrorCategory.DATA_INCOMPLETE: "Check data quality alerts; may need manual intervention.",
        ErrorCategory.DATA_INVALID: "Check data validation logs; schema may have changed.",
        ErrorCategory.DATABASE_ERROR: "Check database connectivity and CloudWatch alarms.",
        ErrorCategory.CONFIGURATION_ERROR: "Verify config in algo_config table.",
        ErrorCategory.DEPENDENCY_FAILED: "Check logs from earlier phases for failure details.",
        ErrorCategory.MARKET_CLOSED: "This is normal outside market hours.",
        ErrorCategory.MARKET_REGIME_HALTED: "Market regime (volatility/breadth) has halted entries.",
        ErrorCategory.EXPOSURE_POLICY_HALTED: "Portfolio exposure limits have halted entries.",
        ErrorCategory.HALT_FLAG_SET: "Data freshness degradation detected; Phase 1 set halt flag.",
        ErrorCategory.TIMEOUT: "Operation took too long; may retry on next run.",
        ErrorCategory.RESOURCE_UNAVAILABLE: "System resource (connection pool, lock) unavailable.",
        ErrorCategory.TEMPORARY_FAILURE: "Transient error; may resolve on retry.",
    }

    return f"{details}. {guidance.get(category, 'Check logs for details.')}"
