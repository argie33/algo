#!/usr/bin/env python3
"""Optional Data Handling Policy - Consistent behavior for missing optional enrichment data.

POLICY:
========
When a loader encounters missing optional data (data not critical to trading):

1. OPTIONAL ENRICHMENT DATA (analyst sentiment, positioning metrics, etc.):
   - Return None to signal "this symbol has no data for this enrichment"
   - Caller uses OptimalLoader framework to handle None returns
   - Log at DEBUG level (not ERROR)
   - Do NOT raise exceptions

2. REQUIRED DATA (prices, technical indicators, trade signals):
   - Raise exceptions immediately with clear error message
   - Include context: symbol, date range, API/table name
   - Let caller decide retry strategy
   - Log at ERROR level

3. DATABASE OPERATIONS:
   - fetchone() returns None if no row → check for None before accessing fields
   - fetchall() returns [] if no rows → check len > 0 before processing
   - Always validate result before indexing: if row: ... else: ...

PATTERNS:
=========

Optional Data (return None):
    >>> def fetch_analyst_coverage(symbol: str) -> dict | None:
    >>>     result = api.get_coverage(symbol)
    >>>     if not result or result.empty:
    >>>         logger.debug(f"No analyst coverage for {symbol}")
    >>>         return None  # Caller handles None gracefully
    >>>     return result.to_dict()

Required Data (raise exception):
    >>> def fetch_price_data(symbol: str) -> list[dict]:
    >>>     prices = db.query("SELECT ... FROM price_daily WHERE symbol = %s", symbol)
    >>>     if not prices:
    >>>         raise RuntimeError(
    >>>             f"No price data found for {symbol}. "
    >>>             f"Price loader may have failed."
    >>>         )
    >>>     return prices

Database NULL handling:
    >>> row = cur.fetchone()
    >>> if row is None:
    >>>     raise RuntimeError("Query returned no rows")
    >>> value = row[0]  # Safe: we know row exists
    >>>
    >>> if row[0] is None:
    >>>     logger.warning("Field was NULL in database")
    >>>     return None  # For optional enrichment
"""

from collections.abc import Callable
from enum import Enum
from typing import Any


class DataCriticality(Enum):
    """Classification of data importance to trading system."""

    CRITICAL = "critical"
    REQUIRED = "required"
    OPTIONAL = "optional"


class OptionalDataSentinel:
    """Sentinel value for "this symbol has no optional data" to distinguish from errors."""

    def __repr__(self) -> str:
        return "<NoOptionalData>"

    def __bool__(self) -> bool:
        return False


NO_OPTIONAL_DATA = OptionalDataSentinel()


def validate_required_data(
    data: Any,
    data_type: str,
    symbol: str | None = None,
    source: str | None = None,
) -> Any:
    """Validate that required data is available; raise if missing.

    Use for CRITICAL and REQUIRED data that blocks trading if unavailable.

    Args:
        data: Data to validate (list, dict, DataFrame, etc.)
        data_type: Human-readable description ("prices", "signals", etc.)
        symbol: Optional symbol for error context
        source: Optional source for error context ("API", "database", etc.)

    Returns:
        data (unchanged) if present

    Raises:
        RuntimeError: If data is None, empty, or invalid
    """
    if data is None or (hasattr(data, "__len__") and len(data) == 0):
        context_parts = [data_type]
        if symbol:
            context_parts.append(f"for {symbol}")
        if source:
            context_parts.append(f"from {source}")

        raise RuntimeError(f"Missing required data: {' '.join(context_parts)}")

    return data


def handle_optional_data(
    data: Any,
    symbol: str | None = None,
    logger_func: Callable[[str], None] | None = None,
    log_message: str | None = None,
) -> Any | None:
    """Handle optional enrichment data gracefully.

    Use for OPTIONAL data that enriches trading but isn't critical.
    Returns None if data unavailable; logs at debug level.

    Args:
        data: Data to check (list, dict, DataFrame, etc.)
        symbol: Optional symbol for logging context
        logger_func: Logger function (e.g., logger.debug); uses print if None
        log_message: Custom message to log; if None, uses default

    Returns:
        data if present, None if missing or empty
    """
    if data is None or (hasattr(data, "__len__") and len(data) == 0):
        if logger_func:
            context = f" for {symbol}" if symbol else ""
            default_msg = f"Skipping optional enrichment{context}"
            logger_func(log_message or default_msg)
        return None

    return data
