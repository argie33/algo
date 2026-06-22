#!/usr/bin/env python3
"""Trading utility helpers for common patterns.

This module consolidates repeated patterns across the trading system:
- Safe Decimal conversions
- Price/quantity conversions
- Error response formatting
- Validation helpers
"""

from decimal import Decimal, InvalidOperation
from typing import Any, overload


@overload
def safe_decimal(value: Any, default: Decimal | float) -> Decimal | float: ...
@overload
def safe_decimal(value: Any, default: Decimal | float | None = ...) -> Decimal | float | None: ...
def safe_decimal(value: Any, default: Any = None) -> Decimal | float | None:
    """Convert value to Decimal safely, returning default on failure.

    Args:
        value: Value to convert (numeric, string, Decimal, or None)
        default: Value to return if conversion fails

    Returns:
        Decimal if conversion succeeds, else default
    """
    if value is None:
        return default  # type: ignore[no-any-return]

    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default  # type: ignore[no-any-return]


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert value to float safely, returning default on failure."""
    if value is None:
        return default

    if isinstance(value, float):
        return value

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Convert value to int safely, returning default on failure."""
    if value is None:
        return default

    if isinstance(value, int) and not isinstance(value, bool):
        return value

    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def error_response(message: str, **extra_fields) -> dict[str, Any]:
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


def success_response(data: Any = None, **extra_fields) -> dict[str, Any]:
    """Create a standardized success response dict."""
    if data is None:
        data = {}

    if isinstance(data, dict):
        return {**data, **extra_fields}

    return {
        "data": data,
        **extra_fields,
    }


def is_error_response(response: dict) -> bool:
    """Check if a response dict is an error response."""
    return "_error" in response or "error" in response


def extract_error(response: dict) -> str | None:
    """Extract error message from response dict."""
    if isinstance(response, dict):
        return response.get("_error") or response.get("error")
    return None
