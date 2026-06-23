#!/usr/bin/env python3
"""Phase data contracts: Schema definitions and validation for inter-phase data passing.

This module defines what data each phase produces and requires, enabling compile-time
safety and explicit dependency tracking. No more silent getattr() defaults.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict

from algo.exceptions import DataContractError, MissingPhaseDataError

logger = logging.getLogger(__name__)

__all__ = [
    "DataContractError",
    "MissingPhaseDataError",
    "Phase1Contract",
    "Phase2Contract",
    "Phase3Contract",
    "Phase4Contract",
    "Phase5Contract",
    "Phase6Contract",
    "PositionRecommendation",
    "validate_dependency_executed",
    "extract_required_data",
]


# Phase 1 produces this schema
class Phase1Contract(TypedDict, total=False):
    """Data contract: what Phase 1 (Data Freshness) produces."""

    status: str  # "ok", "degraded", "warning"
    summary: str
    tables_checked: int
    tables_stale: list[str]


# Phase 2 produces this schema
class Phase2Contract(TypedDict, total=False):
    """Data contract: what Phase 2 (Circuit Breakers) produces."""

    status: str  # "ok", "halted"
    checks: dict[str, dict[str, Any] | None]  # {check_name: {halted, label, reason}}
    breaker_triggered: bool


# Phase 3 produces this schema
class PositionRecommendation(TypedDict, total=False):
    """Schema for position recommendations from Phase 3."""

    action: str  # "HOLD", "RAISE_STOP", "EARLY_EXIT", "FAILED_VALIDATION"
    symbol: str
    position_id: str
    trade_id: str
    current_price: float
    active_stop: float
    new_stop_recommended: float
    action_reason: str


class Phase3Contract(TypedDict):
    """Data contract: what Phase 3 (Position Monitor) produces."""

    recommendations: list[PositionRecommendation]


# Phase 4 produces this schema
class Phase4Contract(TypedDict, total=False):
    """Data contract: what Phase 4 (Position Reconciliation) produces."""

    success: bool
    positions: int
    reason: str


# Phase 5 produces this schema
class ExposureAction(TypedDict, total=False):
    """Schema for exposure policy actions from Phase 5."""

    symbol: str
    position_id: str
    trade_id: str
    action: str  # "force_exit", "partial_exit", "tighten_stop"
    reason: str
    new_stop: float
    exit_fraction: float


class Phase5Contract(TypedDict):
    """Data contract: what Phase 5 (Exposure Policy) produces."""

    constraints: dict[str, Any]
    actions: list[ExposureAction]


# Phase 6 produces this schema
class Phase6Contract(TypedDict, total=False):
    """Data contract: what Phase 6 (Exit Execution) produces."""

    exits_executed: int
    summary: str


# Phase 7 produces this schema
class QualifiedTrade(TypedDict, total=False):
    """Schema for qualified trades from Phase 7."""

    symbol: str
    signal: str
    score: float


class Phase7Contract(TypedDict):
    """Data contract: what Phase 7 (Signal Generation) produces."""

    qualified_trades: list[QualifiedTrade]


# Phase 8 produces this schema
class Phase8Contract(TypedDict, total=False):
    """Data contract: what Phase 8 (Entry Execution) produces."""

    entered: int
    summary: str


# Phase 9 produces this schema
class Phase9Contract(TypedDict, total=False):
    """Data contract: what Phase 9 (Final Reconciliation) produces."""

    positions: int
    summary: str


@dataclass
class PhaseDataSchema:
    """Metadata about what a phase produces."""

    phase_num: int | str
    phase_name: str
    required_keys: list[str] = field(default_factory=list)
    optional_keys: list[str] = field(default_factory=list)

    def validate(self, data: dict[str, Any]) -> None:
        """Validate that data matches this schema.

        Args:
            data: Dictionary to validate

        Raises:
            DataContractError: If validation fails
        """
        if not isinstance(data, dict):
            raise DataContractError(f"Phase {self.phase_num} data must be dict, got {type(data).__name__}")

        missing = [k for k in self.required_keys if k not in data]
        if missing:
            raise DataContractError(
                f"Phase {self.phase_num} ({self.phase_name}) data missing required keys: {missing}. "
                f"Available: {list(data.keys())}"
            )


# Define what each phase produces
PHASE_CONTRACTS = {
    1: PhaseDataSchema(
        1,
        "DATA FRESHNESS CHECK",
        required_keys=["status"],
        optional_keys=["summary", "tables_checked"],
    ),
    2: PhaseDataSchema(
        2,
        "CIRCUIT BREAKERS",
        required_keys=["status"],
        optional_keys=["checks", "breaker_triggered"],
    ),
    3: PhaseDataSchema(3, "POSITION MONITOR", required_keys=["recommendations"]),
    4: PhaseDataSchema(
        4,
        "RECONCILIATION",
        required_keys=["success"],
        optional_keys=["positions", "reason"],
    ),
    # Phase 5 is CRITICAL: constraints MUST be validated separately with validate_phase_5_constraints()
    5: PhaseDataSchema(5, "EXPOSURE POLICY", required_keys=["constraints", "actions"]),
    6: PhaseDataSchema(6, "EXIT EXECUTION", optional_keys=["exits_executed", "summary"]),
    7: PhaseDataSchema(7, "SIGNAL GENERATION", required_keys=["qualified_trades"]),
    8: PhaseDataSchema(8, "ENTRY EXECUTION", optional_keys=["entered", "summary"]),
    9: PhaseDataSchema(9, "RECONCILIATION & SNAPSHOT", optional_keys=["positions", "summary"]),
}


def validate_phase_data(phase_num: int | str, data: dict[str, Any]) -> None:
    """Validate phase data against its contract.

    ISSUE #7 FIX: Validate all phase outputs to prevent silent data loss.
    Fails if phase data is missing required keys.

    Args:
        phase_num: Phase number
        data: Data to validate

    Raises:
        DataContractError: If validation fails
    """
    if phase_num not in PHASE_CONTRACTS:
        logger.debug(f"No schema defined for Phase {phase_num}, skipping validation")
        return

    schema = PHASE_CONTRACTS[phase_num]
    schema.validate(data)


def validate_phase_5_constraints(constraints: dict[str, Any]) -> None:
    """Validate Phase 5 constraints have required fields.

    Phases 7 and 8 depend on these fields for position sizing.
    This is a strict contract: empty or incomplete constraints block downstream phases.

    Args:
        constraints: Dictionary to validate

    Raises:
        DataContractError: If constraints are missing required fields
    """
    if not isinstance(constraints, dict):
        raise DataContractError(f"Phase 5 constraints must be dict, got {type(constraints).__name__}")

    if not constraints:
        raise DataContractError("Phase 5 constraints is empty. Cannot proceed with signal generation.")

    required_fields = ["tier_name", "risk_multiplier", "max_new_positions_today"]
    missing = [f for f in required_fields if f not in constraints]
    if missing:
        raise DataContractError(
            f"Phase 5 constraints missing required fields: {missing}. "
            f"Available: {list(constraints.keys())}. "
            f"Phase 5 must provide all constraint fields for Phase 7/8 to execute."
        )


def validate_dependency_executed(phase_num: int | str, dep_num: int | str, result: Any) -> None:
    """Validate that a dependency phase executed and produced valid data.

    ISSUE #7 FIX: Check both that phase ran AND that it produced valid output.
    Prevents downstream phases from receiving incomplete data.

    Args:
        phase_num: Phase that depends on data
        dep_num: Dependency phase number
        result: PhaseResult from dependency

    Raises:
        MissingPhaseDataError: If dependency failed or data is invalid
    """
    from algo.orchestrator.phase_result import PhaseResult

    if result is None:
        raise MissingPhaseDataError(
            f"Phase {phase_num} depends on Phase {dep_num} but Phase {dep_num} never executed. Dependency chain broken."
        )

    if not isinstance(result, PhaseResult):
        raise MissingPhaseDataError(
            f"Phase {phase_num} depends on Phase {dep_num} but got invalid result type: {type(result).__name__}"
        )

    if not result.ok:
        raise MissingPhaseDataError(
            f"Phase {phase_num} depends on Phase {dep_num} but Phase {dep_num} failed: "
            f"status={result.status}, error={result.error}. "
            f"Cannot proceed without successful Phase {dep_num}."
        )

    # Validate dependency data schema
    try:
        validate_phase_data(dep_num, result.data)
    except DataContractError as e:
        raise MissingPhaseDataError(
            f"Phase {phase_num} depends on Phase {dep_num} but Phase {dep_num}'s data is invalid: {e}"
        ) from e


def extract_required_data(phase_num: int | str, data: dict[str, Any], *keys: str) -> tuple[Any, ...]:
    """Extract required data from phase result with validation.

    ISSUE #7 FIX: Fail explicitly if required data is missing.
    Never silently return None or empty values.

    Args:
        phase_num: Phase that produced this data
        data: Phase result data dictionary
        *keys: Required keys to extract

    Returns:
        Tuple of extracted values (single value if one key)

    Raises:
        DataContractError: If any required key is missing or data is invalid
    """
    if not isinstance(data, dict):
        raise MissingPhaseDataError(f"Phase {phase_num} data must be dict, got {type(data).__name__}")

    missing = [k for k in keys if k not in data]
    if missing:
        raise MissingPhaseDataError(
            f"Phase {phase_num} missing required keys: {missing}. "
            f"Expected: {list(keys)}. Available: {list(data.keys())}"
        )

    result: tuple[Any, ...] = tuple(data[k] for k in keys)
    return result
