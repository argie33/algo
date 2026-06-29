"""Financial Data Validation - Strict fail-fast patterns for finance applications.

CRITICAL PRINCIPLE: In financial systems, absence of data is NOT the same as zero or empty.
Silent failures lead to invalid trading decisions.

This module provides strict validation wrappers that enforce fail-fast behavior for:
1. Data loading (prices, economic metrics, market data)
2. Calculations (position sizing, risk metrics)
3. Portfolio operations (entries, exits, reconciliation)

Use `strict_*()` functions in critical paths. No `.get()` with defaults. No `or []` fallbacks.
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class FinanceValidationError(RuntimeError):
    """Raised when critical financial data is missing, invalid, or inaccessible."""


def strict_get_dict(data: dict[str, Any] | None, key: str, source: str = "") -> Any:
    """Retrieve required dict key. Fail-fast if missing or data is None.

    Args:
        data: Dictionary to access (None raises error)
        key: Required key name
        source: Context for error message (e.g., "prices", "positions")

    Raises:
        FinanceValidationError: If key missing or data is None

    Example:
        # BAD: price = row.get("close", 0)  # Hides missing data
        # GOOD:
        price = strict_get_dict(row, "close", source="price_daily")
    """
    if data is None:
        raise FinanceValidationError(
            f"[{source}] Cannot access key '{key}': data is None. "
            "This indicates upstream data pipeline failure (not zero or empty data)."
        )
    if key not in data:
        raise FinanceValidationError(
            f"[{source}] Required key '{key}' missing from data. "
            f"Available keys: {list(data.keys())}. "
            "Upstream loader must provide all required fields."
        )
    value = data[key]
    if value is None:
        raise FinanceValidationError(
            f"[{source}] Key '{key}' is None (not missing). Database returned null for required field."
        )
    return value


def strict_get_list(data: list[Any] | None, source: str = "") -> list[Any]:
    """Validate list is not None. Fail-fast if None.

    Args:
        data: List to validate (None raises error)
        source: Context for error message

    Raises:
        FinanceValidationError: If data is None

    Example:
        # BAD: for item in items or []:  # Silently processes empty list on None
        # GOOD:
        for item in strict_get_list(items, source="buy_signals"):
    """
    if data is None:
        raise FinanceValidationError(
            f"[{source}] Cannot iterate: data is None. This indicates upstream pipeline failure, not empty result set."
        )
    return data


def strict_get_float(value: float | str | None, source: str = "", context: str = "") -> float:
    """Parse and validate float value. Fail-fast if None, invalid, or zero.

    Args:
        value: Value to parse (string or float)
        source: Field name or context (e.g., "close_price", "position_size")
        context: Additional context (e.g., "symbol=SPY, date=2026-06-26")

    Raises:
        FinanceValidationError: If value is None, not numeric, or zero

    Example:
        # BAD: price = safe_float(row["close"], default=0.0)  # Hides missing price
        # GOOD:
        price = strict_get_float(row["close"], source="close_price", context=f"symbol={sym}")
    """
    if value is None:
        raise FinanceValidationError(f"[{source}] Value is None. {context}. Missing required numeric data.")
    try:
        fv = float(value)
    except (ValueError, TypeError) as e:
        raise FinanceValidationError(f"[{source}] Cannot parse as float: {value!r}. {context}. Error: {e}") from e

    if fv == 0:
        raise FinanceValidationError(
            f"[{source}] Value is zero. {context}. "
            "Zero may indicate missing/invalid data (e.g., price=0, dividend=0). "
            "If zero is expected, validate upstream and pass non-None sentinel."
        )
    if fv < 0 and source not in ("delta", "pnl", "return", "change"):
        raise FinanceValidationError(
            f"[{source}] Value is negative: {fv}. {context}. Prices/quantities should not be negative."
        )
    return fv


def strict_get_int(value: int | str | None, source: str = "", context: str = "", allow_zero: bool = False) -> int:
    """Parse and validate integer value. Fail-fast if None or invalid.

    Args:
        value: Value to parse
        source: Field name or context
        context: Additional context
        allow_zero: If True, zero is acceptable (e.g., for counts)

    Raises:
        FinanceValidationError: If value is None or not an integer
    """
    if value is None:
        raise FinanceValidationError(f"[{source}] Value is None. {context}. Missing required integer data.")
    try:
        iv = int(value)
    except (ValueError, TypeError) as e:
        raise FinanceValidationError(f"[{source}] Cannot parse as int: {value!r}. {context}. Error: {e}") from e

    if iv < 0:
        raise FinanceValidationError(
            f"[{source}] Value is negative: {iv}. {context}. Counts/quantities should not be negative."
        )
    if iv == 0 and not allow_zero:
        raise FinanceValidationError(f"[{source}] Value is zero. {context}. If zero is expected, set allow_zero=True.")
    return iv


def require_non_empty_dict(data: dict[str, Any] | None, source: str = "") -> dict[str, Any]:
    """Validate dict is not None and not empty. Fail-fast if either.

    Args:
        data: Dictionary to validate
        source: Context for error message

    Raises:
        FinanceValidationError: If None or empty
    """
    if data is None:
        raise FinanceValidationError(f"[{source}] Data dict is None. Upstream loader must return valid data structure.")
    if not data:
        raise FinanceValidationError(
            f"[{source}] Data dict is empty. Upstream loader returned empty result (not failure or missing data)."
        )
    return data


def require_non_empty_list(data: list[Any] | None, source: str = "") -> list[Any]:
    """Validate list is not None and not empty. Fail-fast if either.

    Args:
        data: List to validate
        source: Context for error message

    Raises:
        FinanceValidationError: If None or empty
    """
    if data is None:
        raise FinanceValidationError(f"[{source}] Data list is None. Upstream pipeline failed to return valid list.")
    if not data:
        raise FinanceValidationError(f"[{source}] Data list is empty. Upstream query/calculation returned no results.")
    return data


def validate_before_trade(value: Any, field_name: str, validator: Callable[[Any], bool]) -> Any:
    """Generic validator for trade-critical values. Raise on validation failure.

    Args:
        value: Value to validate
        field_name: Name of field (for error messages)
        validator: Callable that returns True if valid

    Raises:
        FinanceValidationError: If validator returns False

    Example:
        position_size = validate_before_trade(
            size, "position_size",
            lambda x: isinstance(x, (int, float)) and x > 0 and x < 10000
        )
    """
    if not validator(value):
        raise FinanceValidationError(
            f"[TRADE_VALIDATION] Field '{field_name}' failed validation: {value!r}. "
            "Trade data must pass all validations before execution."
        )
    return value


# Exported API
__all__ = [
    "FinanceValidationError",
    "require_non_empty_dict",
    "require_non_empty_list",
    "strict_get_dict",
    "strict_get_float",
    "strict_get_int",
    "strict_get_list",
    "validate_before_trade",
]
