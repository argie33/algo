#!/usr/bin/env python3
"""Shared type conversion utilities for loaders.

Eliminates duplication of _safe_float(), _safe_int(), etc. across 6+ loaders.
Provides consistent error handling and logging for metric type conversions.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def safe_float(value: Any, field_name: str, allow_none: bool = True) -> float | None:
    """Safely convert value to float with clear error messages.

    Args:
        value: Value to convert
        field_name: Name of field (for error messages)
        allow_none: If True, return None for None values. If False, raise error.

    Returns:
        Float value or None (if allow_none=True and value is None)

    Raises:
        RuntimeError: If conversion fails and allow_none=False, or if value is not convertible
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError(f"Cannot convert {field_name}: value is None but allow_none=False")

    try:
        return float(value)
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"Cannot convert {field_name} to float: {value!r} ({type(value).__name__}). "
            f"Error: {e}"
        ) from e


def safe_int(value: Any, field_name: str, allow_none: bool = True) -> int | None:
    """Safely convert value to int with clear error messages.

    Args:
        value: Value to convert
        field_name: Name of field (for error messages)
        allow_none: If True, return None for None values. If False, raise error.

    Returns:
        Int value or None (if allow_none=True and value is None)

    Raises:
        RuntimeError: If conversion fails
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError(f"Cannot convert {field_name}: value is None but allow_none=False")

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"Cannot convert {field_name} to int: {value!r} ({type(value).__name__}). "
            f"Error: {e}"
        ) from e


def safe_bool(value: Any, field_name: str, allow_none: bool = True) -> bool | None:
    """Safely convert value to bool with clear error messages.

    Args:
        value: Value to convert (accepts True/False, 1/0, 'true'/'false', etc)
        field_name: Name of field (for error messages)
        allow_none: If True, return None for None values. If False, raise error.

    Returns:
        Bool value or None (if allow_none=True and value is None)

    Raises:
        RuntimeError: If conversion fails
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError(f"Cannot convert {field_name}: value is None but allow_none=False")

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        if value.lower() in ("true", "1", "yes", "y"):
            return True
        if value.lower() in ("false", "0", "no", "n"):
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    raise RuntimeError(
        f"Cannot convert {field_name} to bool: {value!r} ({type(value).__name__}). "
        f"Acceptable values: True/False, 1/0, 'true'/'false', 'yes'/'no'"
    )


def safe_str(value: Any, field_name: str, allow_none: bool = True, strip: bool = True) -> str | None:
    """Safely convert value to str with clear error messages.

    Args:
        value: Value to convert
        field_name: Name of field (for error messages)
        allow_none: If True, return None for None values. If False, raise error.
        strip: If True, strip leading/trailing whitespace

    Returns:
        String value or None (if allow_none=True and value is None)

    Raises:
        RuntimeError: If conversion fails
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError(f"Cannot convert {field_name}: value is None but allow_none=False")

    try:
        result = str(value)
        return result.strip() if strip else result
    except Exception as e:
        raise RuntimeError(
            f"Cannot convert {field_name} to str: {value!r}. Error: {e}"
        ) from e


__all__ = [
    "safe_float",
    "safe_int",
    "safe_bool",
    "safe_str",
]
