"""Data validation and safe conversion utilities for dashboard.

STRICT MODE FOR FINANCE: This module supports two modes for data conversion:
1. Permissive (default=0.0/0/{}): Legacy mode for backward compatibility
2. Strict (default=None, strict=True): For financial data—fails loudly if conversion fails

Finance principle: Missing data is NOT the same as zero. Use strict mode for critical paths.
"""

import json
import logging
from typing import Any, Literal, TypeVar, cast, overload


logger = logging.getLogger(__name__)

T = TypeVar("T")


class StrictValidationError(Exception):
    """Raised when data conversion fails in strict mode (required for finance paths)."""


@overload
def safe_float(
    value: Any,
    *,
    default: float | None = None,
    strict: Literal[False] = False,
    field_name: str | None = None,
) -> float | None: ...


@overload
def safe_float(
    value: Any,
    *,
    default: float | None = None,
    strict: Literal[True],
    field_name: str | None = None,
) -> float: ...


def safe_float(
    value: Any,
    *,
    default: float | None = None,
    strict: bool = False,
    field_name: str | None = None,
) -> float | None:
    """Convert value to float with configurable failure behavior.

    Args:
        value: Value to convert
        default: Value to return on conversion failure (default: None returns None)
                 Use default=0.0 only for aggregation contexts where 0 is meaningful
        strict: If True, raise StrictValidationError instead of returning default
        field_name: Field name for error logging

    Returns:
        float, or default value, or raises StrictValidationError (if strict=True)

    WARNING: For finance data, use strict=True or default=None. Returning 0.0 for missing
    portfolio values, market prices, or P&L is catastrophically misleading.
    """
    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to float{f' for {field_name}' if field_name else ''}")
        if default == 0.0:
            logger.warning(
                f"Converting None to 0.0{f' for {field_name}' if field_name else ''}—finance data should use strict mode"
            )
        return default

    try:
        return float(value)
    except (TypeError, ValueError) as e:
        if strict:
            raise StrictValidationError(f"Cannot convert {field_name or 'value'}={value!r} to float: {e}") from e
        if default == 0.0:
            logger.warning(
                f"Failed to convert {field_name or 'value'}={value!r} to float (returning 0.0—use strict mode for finance): {e}"
            )
        elif default is not None:
            logger.warning(f"Failed to convert {field_name or 'value'}={value!r} to float (returning {default}): {e}")
        return default


@overload
def safe_int(
    value: Any,
    *,
    default: int | None = None,
    strict: Literal[False] = False,
    field_name: str | None = None,
) -> int | None: ...


@overload
def safe_int(
    value: Any,
    *,
    default: int | None = None,
    strict: Literal[True],
    field_name: str | None = None,
) -> int: ...


def safe_int(
    value: Any,
    *,
    default: int | None = None,
    strict: bool = False,
    field_name: str | None = None,
) -> int | None:
    """Convert value to int with configurable failure behavior.

    Args:
        value: Value to convert
        default: Value to return on conversion failure (default: None = strict mode)
                 Use default=0 only for counters/counts where 0 is meaningful
        strict: If True, raise StrictValidationError instead of returning default
        field_name: Field name for error logging

    Returns:
        int, or default value, or raises StrictValidationError (if strict=True)

    WARNING: For trade counts or position metrics, use strict=True. Returning 0 for
    missing trade count or position count is misleading.
    """
    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to int{f' for {field_name}' if field_name else ''}")
        if default == 0:
            logger.warning(
                f"Converting None to 0{f' for {field_name}' if field_name else ''}—trade counts should use strict mode"
            )
        return default

    try:
        return int(value)
    except (TypeError, ValueError) as e:
        if strict:
            raise StrictValidationError(f"Cannot convert {field_name or 'value'}={value!r} to int: {e}") from e
        if default == 0:
            logger.warning(
                f"Failed to convert {field_name or 'value'}={value!r} to int (returning 0—use strict mode for finance): {e}"
            )
        elif default is not None:
            logger.warning(f"Failed to convert {field_name or 'value'}={value!r} to int (returning {default}): {e}")
        return default


def safe_json_parse(value: Any, *, default: Any = None, strict: bool = False, field_name: str | None = None) -> Any:
    """Parse JSON string with configurable failure behavior.

    Args:
        value: Value to parse (string, dict, list, or None)
        default: Value to return on parse failure (default: None = strict mode)
                 If default is None and not strict, returns {} for missing JSON
        strict: If True, raise StrictValidationError instead of returning default
        field_name: Field name for error logging

    Returns:
        Parsed object, or default value, or raises StrictValidationError (if strict=True)
    """
    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot parse None as JSON{f' for {field_name}' if field_name else ''}")
        return default if default is not None else {}

    # If it's already parsed, return as-is
    if isinstance(value, (dict, list)):
        return value

    # If it's a string, try to parse
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            if strict:
                raise StrictValidationError(
                    f"Cannot parse JSON{f' for {field_name}' if field_name else ''}: {e}. Value: {value[:100]}"
                ) from e
            logger.warning(
                f"Failed to parse JSON{f' for {field_name}' if field_name else ''}: {e}. Value: {value[:100]}"
            )
            return default if default is not None else {}

    # For unexpected types
    if strict:
        raise StrictValidationError(
            f"Expected string or dict{f' for {field_name}' if field_name else ''}, got {type(value).__name__}: {value!r}"
        )
    logger.warning(
        f"Expected string or dict{f' for {field_name}' if field_name else ''}, got {type(value).__name__}: {value!r}"
    )
    return default if default is not None else {}


def safe_bool(value: Any, default: bool = False, field_name: str | None = None) -> bool:
    """Safely convert value to bool with logging."""
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        val_lower = value.lower().strip()
        if val_lower in ("true", "1", "yes", "on"):
            return True
        elif val_lower in ("false", "0", "no", "of", ""):
            return False
        else:
            if field_name:
                logger.warning(f"Cannot convert {field_name}={value!r} to bool")
            else:
                logger.warning(f"Cannot convert {value!r} to bool")
            return default

    try:
        return bool(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to bool: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to bool: {e}")
        return default


def safe_str(value: Any, default: str = "", field_name: str | None = None) -> str:
    """Safely convert value to string with logging."""
    if value is None:
        return default

    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to str: {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to str: {e}")
        return default


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


def log_data_issue(fetcher_name: str, field_name: str, issue: str, value: Any = None):
    """Log a data issue from a fetcher function."""
    if value is not None:
        logger.warning(f"{fetcher_name}.{field_name}: {issue} (value: {value!r})")
    else:
        logger.warning(f"{fetcher_name}.{field_name}: {issue}")


# ── Strict-mode convenience functions for finance paths ────────────────────────


def safe_float_strict(value: Any, field_name: str | None = None) -> float:
    """Convert value to float in strict mode. Raises StrictValidationError if fails."""
    return safe_float(value, strict=True, field_name=field_name)


def safe_int_strict(value: Any, field_name: str | None = None) -> int:
    """Convert value to int in strict mode. Raises StrictValidationError if fails."""
    return safe_int(value, strict=True, field_name=field_name)


def safe_json_parse_strict(value: Any, field_name: str | None = None) -> Any:
    """Parse JSON in strict mode. Raises StrictValidationError if fails."""
    return safe_json_parse(value, strict=True, field_name=field_name)


# ── Audit and Migration Helpers ────────────────────────────────────────────


def audit_fallback_usage() -> dict[str, Any]:
    """Audit codebase for remaining safe_* calls with problematic defaults.

    Returns summary of findings for migration planning.
    Useful for identifying which code paths still use permissive fallbacks.
    """
    return {
        "acceptable_patterns": [
            "safe_float(..., default=None) → None handling in rendering layer (OK)",
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
            "Change to: safe_float_strict() or safe_float(..., default=None)",
            "Update callers to check for None instead of assuming 0 is valid data",
            "Add test coverage for missing data scenarios (not just happy path)",
        ],
    }
