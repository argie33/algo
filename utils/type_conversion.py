"""Shared type conversion utilities for loaders.

Consolidates duplicate type-checking code across all data loaders.
Provides fail-fast validation with clear error messages.
"""

import logging
import math
from decimal import Decimal
from typing import Any, Literal, overload

logger = logging.getLogger(__name__)


def _reject_non_finite(value: float, field_name: str) -> float:
    """Raise if value is NaN or +/-Infinity - never let either reach a calculation.

    CRITICAL (2026-07-21 financial-integrity audit): safe_float() is used across ~40 files
    specifically for "fail-fast" numeric conversion, but had no NaN/Infinity check at all -
    isinstance(value, float) returned float('nan') straight through unchanged, and the
    Decimal/str paths accept Decimal("NaN")/float("nan")/float("inf") without error too.
    A NaN silently poisons every comparison downstream (NaN > x and NaN < x are both always
    False, so threshold checks like circuit breaker/exposure-tier gating don't raise, they
    just silently take the "else" branch) and a NUMERIC DB column write with NaN/Infinity
    either errors cryptically or, on some drivers, silently coerces - neither is the loud
    failure a real invalid-data case deserves.
    """
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"[TYPE_CONVERSION] {field_name}={value!r} is not a finite number (NaN/Infinity)")
    return value


@overload
def safe_float(value: Any, field_name: str, allow_none: Literal[True] = True) -> float | None: ...


@overload
def safe_float(value: Any, field_name: str, allow_none: Literal[False]) -> float: ...


def safe_float(value: Any, field_name: str, allow_none: bool = True) -> float | None:
    """Safely convert value to float with fail-fast validation.

    Args:
        value: Value to convert (can be None, float, int, string, or Decimal)
        field_name: Name of field for error reporting (e.g., "AAPL.roe")
        allow_none: If True, returns None for None input; if False, raises error

    Returns:
        Float value or None (if allow_none=True and value is None)

    Raises:
        ValueError: If value cannot be converted to float or if type is invalid
        TypeError: If value is bool (often a data corruption indicator)
    """
    if isinstance(value, bool):
        raise TypeError(
            f"[TYPE_CONVERSION] Cannot convert {field_name}={value!r}: got bool (data corruption?). "
            f"Expected numeric or None."
        )

    if value is None:
        if allow_none:
            return None
        raise ValueError(f"[TYPE_CONVERSION] {field_name}=None but None not allowed")

    if isinstance(value, float):
        return _reject_non_finite(value, field_name)

    if isinstance(value, int):
        return float(value)

    if isinstance(value, Decimal):
        return _reject_non_finite(float(value), field_name)

    if isinstance(value, str):
        try:
            return _reject_non_finite(float(value), field_name)
        except ValueError as e:
            raise ValueError(f"[TYPE_CONVERSION] Cannot parse {field_name}={value!r} as float: {e}") from e

    raise TypeError(
        f"[TYPE_CONVERSION] Cannot convert {field_name}={value!r} (type={type(value).__name__}). "
        f"Expected numeric, string, or None."
    )


@overload
def safe_int(value: Any, field_name: str, allow_none: Literal[True] = True) -> int | None: ...


@overload
def safe_int(value: Any, field_name: str, allow_none: Literal[False]) -> int: ...


def safe_int(value: Any, field_name: str, allow_none: bool = True) -> int | None:
    """Safely convert value to int with fail-fast validation."""
    if isinstance(value, bool):
        raise TypeError(f"[TYPE_CONVERSION] {field_name}: got bool, expected int")

    if value is None:
        if allow_none:
            return None
        raise ValueError(f"[TYPE_CONVERSION] {field_name}=None but None not allowed")

    if isinstance(value, int):
        return value

    if isinstance(value, Decimal):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as e:
            raise ValueError(f"[TYPE_CONVERSION] Cannot parse {field_name}={value!r} as int: {e}") from e

    raise TypeError(
        f"[TYPE_CONVERSION] Cannot convert {field_name}={value!r} (type={type(value).__name__}). "
        f"Expected int, string, or None."
    )


@overload
def safe_bool(value: Any, field_name: str, allow_none: Literal[True] = True) -> bool | None: ...


@overload
def safe_bool(value: Any, field_name: str, allow_none: Literal[False]) -> bool: ...


def safe_bool(value: Any, field_name: str, allow_none: bool = True) -> bool | None:
    """Safely convert value to bool with fail-fast validation."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"[TYPE_CONVERSION] {field_name}=None but None not allowed")

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"[TYPE_CONVERSION] {field_name}={value}: int must be 0 or 1 for bool conversion")

    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        raise ValueError(f"[TYPE_CONVERSION] {field_name}={value!r}: unknown bool value")

    raise TypeError(
        f"[TYPE_CONVERSION] Cannot convert {field_name}={value!r} (type={type(value).__name__}). "
        f"Expected bool, 0/1, or string."
    )


@overload
def safe_string(
    value: Any, field_name: str, allow_none: Literal[True] = True, max_len: int | None = None
) -> str | None: ...


@overload
def safe_string(value: Any, field_name: str, allow_none: Literal[False], max_len: int | None = None) -> str: ...


def safe_string(value: Any, field_name: str, allow_none: bool = True, max_len: int | None = None) -> str | None:
    """Safely convert value to string with optional length validation."""
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"[TYPE_CONVERSION] {field_name}=None but None not allowed")

    if isinstance(value, str):
        result = value
    else:
        result = str(value)

    if max_len and len(result) > max_len:
        raise ValueError(f"[TYPE_CONVERSION] {field_name}={result!r}: length {len(result)} exceeds max {max_len}")

    return result
