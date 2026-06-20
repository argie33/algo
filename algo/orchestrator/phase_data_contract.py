#!/usr/bin/env python3
"""Phase data contracts: Schema definitions and validation for inter-phase data passing.

This module defines what data each phase produces and requires, enabling compile-time
safety and explicit dependency tracking. No more silent getattr() defaults.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, TypedDict


logger = logging.getLogger(__name__)


class DataContractError(Exception):
    """Raised when phase data does not match required schema."""



class MissingPhaseDataError(DataContractError):
    """Raised when required phase data is not available (phase didn't run or failed)."""



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
    """Data contract: what Phase 3 produces."""

    recommendations: list[PositionRecommendation]
    count: int


# Phase 3b produces this schema
class ExposureAction(TypedDict, total=False):
    """Schema for exposure policy actions from Phase 3b."""

    symbol: str
    position_id: str
    trade_id: str
    action: str  # "force_exit", "partial_exit", "tighten_stop"
    reason: str
    new_stop: float
    exit_fraction: float


class Phase3bContract(TypedDict):
    """Data contract: what Phase 3b produces."""

    constraints: dict[str, Any]
    actions: list[ExposureAction]


# Phase 5 produces this schema
class QualifiedTrade(TypedDict, total=False):
    """Schema for qualified trades from Phase 5."""

    symbol: str
    signal: str
    score: float


class Phase5Contract(TypedDict):
    """Data contract: what Phase 5 produces."""

    qualified_trades: list[QualifiedTrade]


@dataclass
class PhaseDataSchema:
    """Metadata about what a phase produces."""

    phase_num: int | str
    phase_name: str
    required_keys: list[str] = field(default_factory=list)

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
            raise DataContractError(f"Phase {self.phase_num} data missing required keys: {missing}")


# Define what each phase produces
PHASE_CONTRACTS = {
    3: PhaseDataSchema(3, "POSITION MONITOR", ["recommendations"]),
    "3b": PhaseDataSchema("3b", "EXPOSURE POLICY", ["constraints", "actions"]),
    5: PhaseDataSchema(5, "SIGNAL GENERATION", ["qualified_trades"]),
}


def validate_phase_3b_constraints(constraints: dict) -> None:
    """Validate Phase 3b constraints have required fields.

    Phase 5 depends on these fields for position sizing.

    Raises:
        DataContractError: If constraints are missing required fields
    """
    if not isinstance(constraints, dict):
        raise DataContractError(f"Phase 3b constraints must be dict, got {type(constraints).__name__}")

    if not constraints:
        raise DataContractError("Phase 3b constraints is empty. Cannot proceed with signal generation.")

    required_fields = ["tier_name", "risk_multiplier", "max_new_positions_today"]
    missing = [f for f in required_fields if f not in constraints]
    if missing:
        raise DataContractError(f"Phase 3b constraints missing required fields: {missing}")


def validate_phase_data(phase_num: int | str, data: dict[str, Any]) -> None:
    """Validate phase data against its contract.

    Args:
        phase_num: Phase number
        data: Data to validate

    Raises:
        DataContractError: If validation fails
    """
    if phase_num in PHASE_CONTRACTS:
        PHASE_CONTRACTS[phase_num].validate(data)


def extract_required_data(phase_num: int | str, data: dict[str, Any], *keys: str) -> tuple[Any, ...]:
    """Extract required data from phase result with validation.

    Args:
        phase_num: Phase that produced this data
        data: Phase result data dictionary
        *keys: Required keys to extract

    Returns:
        Tuple of extracted values

    Raises:
        DataContractError: If any required key is missing or data is invalid
    """
    if not isinstance(data, dict):
        raise DataContractError(f"Phase {phase_num} data must be dict, got {type(data).__name__}")

    missing = [k for k in keys if k not in data]
    if missing:
        raise DataContractError(
            f"Phase {phase_num} missing required keys: {missing}. Available keys: {list(data.keys())}"
        )

    return tuple(data[k] for k in keys)
