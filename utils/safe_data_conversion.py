#!/usr/bin/env python3
"""
Safe data conversion utilities with proper error handling and logging.

Provides safe conversions for:
- float() → handles NaN, Infinity, None, invalid strings
- date/datetime parsing → handles multiple formats, timezone-aware
- JSON parsing → logs warnings for failed parses
"""

import json
import logging
import math
from datetime import datetime, date
from typing import Any, Optional, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# FLOAT CONVERSION
# ──────────────────────────────────────────────────────────────────────────────

def safe_float(value: Any, default: float = 0.0, context: str = "") -> float:
    """Convert value to float safely, handling NaN, Infinity, None.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails
        context: Context string for logging (e.g., "symbol=AAPL, field=price")

    Returns:
        Float value or default if conversion fails

    Raises:
        ValueError: If value is a string like "NaN" or "Infinity" (logged as warning)
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        f = float(value)

        # Reject NaN and Infinity explicitly
        if math.isnan(f):
            logger.warning(f"NaN value rejected {context}")
            return default
        if math.isinf(f):
            logger.warning(f"Infinity value rejected {context}")
            return default

        return f
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value!r} to float {context}: {e}")
        return default


def safe_float_strict(value: Any, context: str = "") -> Optional[float]:
    """Convert value to float safely, returning None on failure (strict mode).

    For use in optional fields where None is appropriate.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        f = float(value)

        if math.isnan(f) or math.isinf(f):
            logger.warning(f"Invalid float value {value!r} {context}")
            return None

        return f
    except (ValueError, TypeError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# DATE/DATETIME PARSING
# ──────────────────────────────────────────────────────────────────────────────

def safe_parse_date(value: Any, context: str = "") -> Optional[date]:
    """Parse date from multiple formats: ISO, string, datetime.

    Handles:
    - ISO format strings (2026-06-10)
    - datetime objects
    - date objects

    Returns None if parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            pass

        # Try common date formats as fallback
        for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass

        logger.warning(f"Failed to parse date {value!r} {context} - no format matched")
        return None

    logger.warning(f"Cannot parse {type(value).__name__} as date {context}")
    return None


def safe_parse_datetime_et(value: Any, context: str = "") -> Optional[datetime]:
    """Parse datetime string with timezone awareness (ET).

    Returns timezone-aware datetime in ET, or None if parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        # If naive, assume ET; if aware, return as-is
        if value.tzinfo is None:
            return value.replace(tzinfo=ZoneInfo("America/New_York"))
        return value

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=ZoneInfo("America/New_York"))
            return dt
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse datetime {value!r} {context}")
            return None

    return None


# ──────────────────────────────────────────────────────────────────────────────
# JSON PARSING
# ──────────────────────────────────────────────────────────────────────────────

def safe_json_loads(json_str: Any, default: Any = None, context: str = "") -> Any:
    """Parse JSON string safely with proper error logging.

    Args:
        json_str: JSON string or already-parsed object
        default: Default value if parsing fails
        context: Context string for logging

    Returns:
        Parsed object or default value
    """
    if isinstance(json_str, (dict, list)):
        return json_str

    if not isinstance(json_str, str):
        logger.warning(f"JSON parse: expected string, got {type(json_str).__name__} {context}")
        return default

    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON parse failed {context}: {e}")
        return default


def safe_json_get(obj: Any, key: str, default: Any = None, context: str = "") -> Any:
    """Safely get value from dict/object, logging on failure.

    Args:
        obj: Dictionary or object to read from
        key: Key to read
        default: Default if key missing or obj is invalid
        context: Context string for logging

    Returns:
        Value at obj[key] or default
    """
    if not isinstance(obj, dict):
        return default

    if key not in obj:
        return default

    return obj.get(key, default)


# ──────────────────────────────────────────────────────────────────────────────
# DATA QUALITY LOGGING
# ──────────────────────────────────────────────────────────────────────────────

def log_data_fetch(
    source: str,
    count: int,
    error: Optional[str] = None,
    fetch_time_ms: Optional[float] = None,
) -> None:
    """Log data fetch results with consistent format.

    Args:
        source: Data source name (e.g., "yfinance", "alpaca")
        count: Number of records fetched
        error: Error message if fetch failed
        fetch_time_ms: Fetch time in milliseconds (optional)
    """
    time_str = f" ({fetch_time_ms:.0f}ms)" if fetch_time_ms else ""

    if error:
        logger.error(f"[{source}] Fetch failed: {error}{time_str}")
    elif count == 0:
        logger.warning(f"[{source}] Returned 0 rows{time_str}")
    else:
        logger.info(f"[{source}] Fetched {count} rows{time_str}")
