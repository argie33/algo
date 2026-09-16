#!/usr/bin/env python3
"""Shared type conversion helpers for orchestrator phase executors.

Centralized conversion logic for psycopg2/database types (Decimal, numpy.int64)
to native Python types (int, float). Prevents duplication across phase files.
"""

from decimal import Decimal
from typing import Any


def ensure_int(val: Any, field_name: str = "value") -> int:
    """Convert any integer value to native Python int with diagnostic logging."""
    if val is None:
        raise ValueError(f"Cannot convert None {field_name} to int")
    try:
        if isinstance(val, Decimal):
            result = int(str(val))
        elif isinstance(val, int) and not isinstance(val, bool):
            result = val
        else:
            result = int(val)
        native_int = int(result)
        if not isinstance(native_int, int) or isinstance(native_int, bool):
            raise TypeError(f"{field_name}: int() returned {type(native_int).__name__}, cannot force to native int")
        return native_int
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: Cannot convert {type(val).__name__} to native Python int: {e}") from e


REAL_ESTATE_SECTOR_CAP_KEY = "Real Estate"


def sector_position_cap(config: dict[str, Any], sector: str | None, global_cap: int) -> int:
    """Resolve the effective max-positions-per-sector cap for one sector.

    Sector-specific override lookup (REAL_ESTATE_SECTOR_CAP_KEY only, as of 2026-09-11 -
    see reit_sector_concentration_cap_added_20260911 in memory): the generic
    max_positions_per_sector gate (entry-side phase8_entry_execution.py, exit-side backstop
    phase6_exit_execution.py) is a flat 8-of-20 (40%) ceiling that doesn't bind at the
    concentration levels this session's live leaderboard pull found (Real Estate 14% of
    top-50, confirmed underperforming while overweighted - see
    reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911 and the three
    scoring-math fixes rejected after it). A global cap tight enough to bind Real Estate
    would also constrain Financial Services' confirmed-DESERVED overweighting
    (financial_services_pillar_concentration_deserved_not_artifact_20260911) - this
    per-sector override targets only the sector with the evidenced problem.

    Fails CLOSED to global_cap on any missing/malformed override (never silently
    disables the gate, never raises into the caller - both call sites already have their
    own fail-open/fail-fast handling around the global cap itself, this only narrows one
    sector's effective limit when it can).
    """
    if sector != REAL_ESTATE_SECTOR_CAP_KEY:
        return global_cap
    override_val = config.get("max_positions_per_sector_real_estate")
    if override_val is None:
        return global_cap
    try:
        return ensure_int(override_val, "max_positions_per_sector_real_estate")
    except (TypeError, ValueError):
        return global_cap


def ensure_float(val: Any, field_name: str = "value") -> float:
    """Convert any numeric value to native Python float, handling psycopg2 Decimal types."""
    if val is None:
        raise ValueError(f"Cannot convert None {field_name} to float")
    try:
        result = float(str(val))
        native_float = float(result)
        if not isinstance(native_float, float) or isinstance(native_float, bool):
            raise TypeError(f"{field_name}: conversion returned {type(native_float).__name__}, not native float")
        return native_float
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field_name}: Cannot convert {type(val).__name__} to native Python float: {e}") from e
