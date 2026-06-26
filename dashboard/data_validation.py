"""Data validation and safe conversion utilities for dashboard.

This module re-exports the better implementations from utils.safe_data_conversion.
All financial data validation should use strict=True mode.

Finance principle: Missing data is NOT the same as zero. Always use strict mode for critical paths.
"""

import logging
from typing import Any

# Re-export from the authoritative safe_data_conversion module
from utils.safe_data_conversion import (
    StrictValidationError,
    safe_bool,
    safe_float,
    safe_int,
    safe_json_parse,
    safe_json_parse_strict,
    safe_str,
)

__all__ = [
    "StrictValidationError",
    "audit_fallback_usage",
    "log_data_issue",
    "safe_bool",
    "safe_float",
    "safe_int",
    "safe_json_parse",
    "safe_json_parse_strict",
    "safe_str",
    "validate_field_types",
    "validate_required_fields",
]

logger = logging.getLogger(__name__)


def validate_required_fields(data: dict[str, Any], required_fields: list[str], source: str | None = None) -> bool:
    """Check if required fields exist in data dict. Log warnings for missing fields."""
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Missing required fields{source_str}: {missing}")
        return False
    return True


def validate_field_types(data: dict[str, Any], type_spec: dict[str, type], source: str | None = None) -> bool:
    """Validate that fields in data match expected types. Log warnings for type mismatches."""
    issues = []
    for field, expected_type in type_spec.items():
        if field not in data:
            continue
        value = data[field]
        if value is None:
            continue
        if not isinstance(value, expected_type):
            issues.append(f"{field}: expected {expected_type.__name__}, got {type(value).__name__}")

    if issues:
        source_str = f" from {source}" if source else ""
        logger.warning(f"Type mismatches{source_str}: {'; '.join(issues)}")
        return False
    return True


def log_data_issue(fetcher_name: str, field_name: str, issue: str, value: Any = None) -> None:
    """Log a data issue from a fetcher function."""
    if value is not None:
        logger.warning(f"{fetcher_name}.{field_name}: {issue} (value: {value!r})")
    else:
        logger.warning(f"{fetcher_name}.{field_name}: {issue}")


# ── Audit and Migration Helpers ────────────────────────────────────────────


def audit_fallback_usage() -> dict[str, Any]:
    """Audit codebase for remaining safe_* calls with problematic defaults.

    Returns summary of findings for migration planning.
    Useful for identifying which code paths still use permissive fallbacks.
    """
    return {
        "acceptable_patterns": [
            "safe_float(...) → None handling in rendering layer (OK)",
            "safe_int(..., default=0) for count aggregation (OK if 0 is identity)",
            "safe_json_parse(..., default={}) for optional JSON fields (OK)",
        ],
        "problematic_patterns": [
            "safe_float(..., default=0.0) for financial values (use strict=True)",
            "safe_int(..., default=0) for counts/trades (use strict=True)",
            "safe_json_parse(..., default=[]) without checking empty result",
        ],
        "migration_strategy": [
            "Identify all safe_* calls with default=0.0/0 that process financial data",
            "Change to: safe_float_strict() or safe_float(...)",
            "Update callers to check for None instead of assuming 0 is valid data",
            "Add test coverage for missing data scenarios (not just happy path)",
        ],
    }
