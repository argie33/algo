#!/usr/bin/env python3
"""Trading utility helpers for common patterns.

This module consolidates repeated patterns across the trading system:
- Safe Decimal conversions
- Price/quantity conversions
- Error response formatting
- Validation helpers
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, overload

logger = logging.getLogger(__name__)


@overload
def safe_decimal(value: Any, allow_none: Literal[False] = False) -> Decimal: ...


@overload
def safe_decimal(value: Any, allow_none: Literal[True]) -> Decimal | None: ...


def safe_decimal(value: Any, allow_none: bool = False) -> Decimal | None:
    """Convert value to Decimal, raising on failure if not allowed.

    Args:
        value: Value to convert (numeric, string, Decimal, or None)
        allow_none: If True, return None on failure (safe mode). If False,
                   raise RuntimeError (fail-fast mode for trading contexts).

    Returns:
        Decimal if conversion succeeds. If allow_none=False (default for trading),
        raises RuntimeError on any failure.

    Raises:
        RuntimeError: If conversion fails and allow_none=False
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError("decimal conversion received None value — required data missing")
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        if allow_none:
            logger.warning(f"safe_decimal conversion failed for {value!r}: {type(e).__name__}")
            return None
        raise RuntimeError(
            f"[DECIMAL_CONVERSION_FAILED] Cannot convert {value!r} to Decimal: {type(e).__name__}. "
            f"This value is required for position sizing — cannot proceed with incomplete data."
        ) from e


def safe_float(value: Any, allow_none: bool = False) -> float | None:
    """Convert value to float, raising on failure if not allowed.

    Args:
        value: Value to convert (numeric, string, or None)
        allow_none: If True, return None on failure (safe mode). If False,
                   raise RuntimeError (fail-fast mode for trading contexts).

    Returns:
        float if conversion succeeds. If allow_none=False, raises on failure.

    Raises:
        RuntimeError: If conversion fails and allow_none=False
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError("float conversion received None value — required data missing")

    if isinstance(value, float):
        return value

    try:
        return float(value)
    except (ValueError, TypeError) as e:
        if allow_none:
            logger.warning(f"safe_float conversion failed for {value!r}: {type(e).__name__}")
            return None
        raise RuntimeError(
            f"[FLOAT_CONVERSION_FAILED] Cannot convert {value!r} to float: {type(e).__name__}. "
            f"This value is required for trading calculations — cannot proceed with incomplete data."
        ) from e


def safe_int(value: Any, allow_none: bool = False) -> int | None:
    """Convert value to int, raising on failure if not allowed.

    Args:
        value: Value to convert (numeric, string, or None)
        allow_none: If True, return None on failure (safe mode). If False,
                   raise RuntimeError (fail-fast mode for trading contexts).

    Returns:
        int if conversion succeeds. If allow_none=False, raises on failure.

    Raises:
        RuntimeError: If conversion fails and allow_none=False
    """
    if value is None:
        if allow_none:
            return None
        raise RuntimeError("int conversion received None value — required data missing")

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        if allow_none:
            logger.warning(f"safe_int conversion failed for {value!r}: {type(e).__name__}")
            return None
        raise RuntimeError(
            f"[INT_CONVERSION_FAILED] Cannot convert {value!r} to int: {type(e).__name__}. "
            f"This value is required for position sizing — cannot proceed with incomplete data."
        ) from e


def error_response(message: str, **extra_fields: Any) -> dict[str, Any]:
    """Create a standardized error response dict.

    Args:
        message: Error message
        **extra_fields: Additional fields to include

    Returns:
        Dict with _error key and optional extra fields
    """
    return {
        "_error": message,
        **extra_fields,
    }


def success_response(data: Any = None, **extra_fields: Any) -> dict[str, Any]:
    """Create a standardized success response dict."""
    if data is None:
        data = {}

    if isinstance(data, dict):
        return {**data, **extra_fields}

    return {
        "data": data,
        **extra_fields,
    }


def is_error_response(response: dict[str, Any]) -> bool:
    """Check if a response dict is an error response."""
    return "_error" in response or "error" in response


def extract_error(response: dict[str, Any]) -> str | None:
    """Extract error message from response dict.

    Returns error message if present in _error or error field, None otherwise.
    Raises ValueError if response is not a dict (malformed response).
    """
    if not isinstance(response, dict):
        raise ValueError(f"Expected dict response, got {type(response).__name__}: {response!r}")
    if "_error" in response:
        return str(response["_error"])
    if "error" in response:
        return str(response["error"])
    return None
