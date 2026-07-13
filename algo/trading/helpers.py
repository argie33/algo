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
from typing import Any

logger = logging.getLogger(__name__)


def safe_decimal(value: Any, field_name: str = "value") -> Decimal:
    """Convert value to Decimal, raising on failure.

    CRITICAL: Always fails fast. Never returns None. For position sizing and risk calculations.
    Uses centralized utils/type_conversion.py for consistent conversion.

    Args:
        value: Value to convert (numeric, string, Decimal)
        field_name: Field name for error reporting

    Returns:
        Decimal if conversion succeeds.

    Raises:
        RuntimeError: If conversion fails or value is None
    """
    if value is None:
        raise RuntimeError(f"[DECIMAL_CONVERSION_FAILED] {field_name} is required but got None")
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise RuntimeError(
            f"[DECIMAL_CONVERSION_FAILED] Cannot convert {field_name}={value!r} to Decimal: {type(e).__name__}. "
            f"This value is required for position sizing — cannot proceed with incomplete data."
        ) from e


def safe_float(value: Any, field_name: str = "value") -> float:
    """Convert value to float, raising on failure.

    CRITICAL: Always fails fast. Never returns None. For price calculations and metrics.
    Uses centralized utils/type_conversion.py with allow_none=False for strict mode.

    Args:
        value: Value to convert (numeric or string)
        field_name: Field name for error reporting

    Returns:
        float if conversion succeeds.

    Raises:
        ValueError/TypeError: If conversion fails or value is None
    """
    from utils.type_conversion import safe_float as canonical_safe_float

    result = canonical_safe_float(value, field_name, allow_none=False)
    if result is None:
        raise RuntimeError(f"[FLOAT_CONVERSION_FAILED] {field_name} is required but got None")
    return result


def safe_int(value: Any, field_name: str = "value") -> int:
    """Convert value to int, raising on failure.

    CRITICAL: Always fails fast. Never returns None. For share quantities and counts.
    Uses centralized utils/type_conversion.py with allow_none=False for strict mode.

    Args:
        value: Value to convert (numeric or string)
        field_name: Field name for error reporting

    Returns:
        int if conversion succeeds.

    Raises:
        ValueError/TypeError: If conversion fails or value is None
    """
    from utils.type_conversion import safe_int as canonical_safe_int

    result = canonical_safe_int(value, field_name, allow_none=False)
    if result is None:
        raise RuntimeError(f"[INT_CONVERSION_FAILED] {field_name} is required but got None")
    return result


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
