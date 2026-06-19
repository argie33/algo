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
from datetime import date, datetime, timezone
from typing import Any


logger = logging.getLogger(__name__)

# Eastern timezone for market hours
EASTERN_TZ = timezone.utc

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
        ValueError: If value is NaN or Infinity (fails fast — required for calculations like position sizing)
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        f = float(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value!r} to float {context}: {e}")
        return default

    # Reject NaN and Infinity explicitly — fail fast instead of silently returning 0.0.
    # Position sizing, risk calculations, and other critical paths require valid data.
    # Silent degradation to 0.0 masks data errors that should be fixed, not ignored.
    if math.isnan(f):
        msg = f"NaN value in critical calculation {context} — data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)
    if math.isinf(f):
        msg = f"Infinity value in critical calculation {context} — data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)

    return f


def safe_float_strict(value: Any, context: str = "") -> float | None:
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
# INT CONVERSION
# ──────────────────────────────────────────────────────────────────────────────


def safe_int(value: Any, default: int = 0, context: str = "") -> int:
    """Convert value to int safely, handling None, invalid strings.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails
        context: Context string for logging

    Returns:
        Int value or default if conversion fails
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return default

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value!r} to int {context}: {e}")
        return default


def safe_int_strict(value: Any, context: str = "") -> int | None:
    """Convert value to int safely, returning None on failure (strict mode).

    For use in optional fields where None is appropriate.

    Args:
        value: Value to convert (can be str, int, float, None)
        context: Context string for logging

    Returns:
        Int value or None if conversion fails
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Failed to convert {value!r} to int (strict) {context}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# DATE/DATETIME PARSING
# ──────────────────────────────────────────────────────────────────────────────


def safe_parse_date(value: Any, context: str = "") -> date | None:
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


def safe_parse_datetime_et(value: Any, context: str = "") -> datetime | None:
    """Parse datetime string with timezone awareness (ET).

    Returns timezone-aware datetime in ET, or None if parsing fails.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        # If naive, assume ET; if aware, return as-is
        if value.tzinfo is None:
            return value.replace(tzinfo=EASTERN_TZ)
        return value

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=EASTERN_TZ)
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
        logger.warning(
            f"JSON parse: expected string, got {type(json_str).__name__} {context}"
        )
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
    error: str | None = None,
    fetch_time_ms: float | None = None,
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


def log_loader_completion(
    table_name: str,
    rows_inserted: int,
    rows_skipped: int = 0,
    rows_failed: int = 0,
    duration_sec: float = 0.0,
) -> None:
    """Log loader completion with summary statistics.

    Args:
        table_name: Target table being loaded
        rows_inserted: Number of rows successfully inserted
        rows_skipped: Number of rows skipped due to duplicates/staleness
        rows_failed: Number of rows that failed validation
        duration_sec: Loader execution time in seconds
    """
    total = rows_inserted + rows_skipped + rows_failed
    if total == 0:
        logger.warning(f"[{table_name}] No data processed")
        return

    duration_str = f" ({duration_sec:.1f}s)" if duration_sec > 0 else ""

    if rows_failed > 0:
        logger.error(
            f"[{table_name}] Loaded {rows_inserted}/{total} rows "
            f"({rows_skipped} skipped, {rows_failed} FAILED){duration_str}"
        )
    elif rows_inserted == 0:
        logger.warning(
            f"[{table_name}] No new rows inserted "
            f"({rows_skipped} skipped, {rows_failed} failed){duration_str}"
        )
    else:
        logger.info(
            f"[{table_name}] Loaded {rows_inserted}/{total} rows "
            f"({rows_skipped} skipped){duration_str}"
        )
