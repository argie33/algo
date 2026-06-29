#!/usr/bin/env python3
"""
Safe data conversion utilities with proper error handling and logging.

Provides safe conversions for:
- float() → handles NaN, Infinity, None, invalid strings
- date/datetime parsing → handles multiple formats, timezone-aware
- JSON parsing → logs warnings for failed parses

FAIL-FAST DESIGN (No Faker/Fallback Patterns):
- Removed secondary source fallbacks: safe_json_parse no longer silently defaults to {}
- Removed silent empty string defaults: safe_str now returns None when no default given
- Removed implicit False defaults: safe_bool now returns None when no default given
- All functions log explicit failures when returning None (caller visibility)
- Strict mode available for all critical paths: use strict=True for finance calculations
- No secondary sources or synthetic data — if data is missing, it's explicitly None or raises

See steering/GOVERNANCE.md for fail-fast design and credential handling rules.

CHANGES SUMMARY (2026-06-29):
- Removed secondary source fallbacks from safe_json_parse (no more empty dict defaults)
- Removed silent empty string defaults from safe_str (default now None)
- Removed implicit False defaults from safe_bool (default now None)
- Enhanced safe_json_get with explicit logging for missing keys
- Updated safe_json_parse_strict with comprehensive documentation
"""

import json
import logging
import math
from datetime import date, datetime, timezone
from typing import Any, overload

logger = logging.getLogger(__name__)


class StrictValidationError(Exception):
    """Raised when data conversion fails in strict mode (required for finance paths)."""


# Eastern timezone for market hours
EASTERN_TZ = timezone.utc

# ──────────────────────────────────────────────────────────────────────────────
# FLOAT CONVERSION
# ──────────────────────────────────────────────────────────────────────────────


@overload
def safe_float(
    value: Any,
    default: float,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> float: ...


@overload
def safe_float(
    value: Any,
    default: None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> float | None: ...


@overload
def safe_float(
    value: Any,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> float | None: ...


def safe_float(
    value: Any,
    default: float | None = None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> float | None:
    """Convert value to float safely, handling NaN, Infinity, None.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (None to require explicit handling; use strict=True for finance)
        context: Context string for logging (e.g., "symbol=AAPL, field=price")
        strict: If True, raise StrictValidationError instead of returning default (REQUIRED for all finance paths)
        field_name: Field name for error logging (preferred over context for new code)

    Returns:
        Float value or default if conversion fails

    Raises:
        ValueError: If value is NaN or Infinity (always fails fast — required for calculations)
        StrictValidationError: If strict=True and conversion fails
    """
    # Use field_name if provided, otherwise fall back to context
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to float {error_ctx}")
        if default is None:
            logger.warning(f"None value in float conversion {error_ctx} — returning None (must be handled by caller)")
        else:
            logger.warning(f"Converting None to {default} {error_ctx}—explicitly requested default")
        return default

    if isinstance(value, bool):
        if strict:
            raise StrictValidationError(f"Cannot convert bool to float {error_ctx}")
        return default

    try:
        f = float(value)
    except (ValueError, TypeError) as e:
        if strict:
            raise StrictValidationError(
                f"Cannot convert {field_name or 'value'}={value!r} to float {error_ctx}: {e}"
            ) from e
        if default is None:
            logger.warning(
                f"Failed to convert {value!r} to float {error_ctx} (returning None—caller must handle missing data): {e}"
            )
        else:
            logger.warning(f"Failed to convert {value!r} to float {error_ctx} (returning {default}): {e}")
        return default

    # Reject NaN and Infinity explicitly — fail fast instead of silently returning 0.0.
    # Position sizing, risk calculations, and other critical paths require valid data.
    # Silent degradation to 0.0 masks data errors that should be fixed, not ignored.
    if math.isnan(f):
        msg = f"NaN value in critical calculation {error_ctx} — data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)
    if math.isinf(f):
        msg = f"Infinity value in critical calculation {error_ctx} — data error must be fixed"
        logger.error(msg)
        raise ValueError(msg)

    return f


# ──────────────────────────────────────────────────────────────────────────────
# INT CONVERSION
# ──────────────────────────────────────────────────────────────────────────────


@overload
def safe_int(
    value: Any,
    default: int,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> int: ...


@overload
def safe_int(
    value: Any,
    default: None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> int | None: ...


@overload
def safe_int(
    value: Any,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> int | None: ...


def safe_int(
    value: Any,
    default: int | None = None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> int | None:
    """Convert value to int safely, handling None, invalid strings.

    Args:
        value: Value to convert (can be str, int, float, None)
        default: Default value if conversion fails (None to require explicit handling; use strict=True for finance)
        context: Context string for logging (deprecated, use field_name)
        strict: If True, raise StrictValidationError instead of returning default (REQUIRED for all finance paths)
        field_name: Field name for error logging

    Returns:
        Int value or default if conversion fails

    Raises:
        StrictValidationError: If strict=True and conversion fails
    """
    error_ctx = f"for {field_name}" if field_name else context

    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot convert None to int {error_ctx}")
        if default is None:
            logger.warning(f"None value in int conversion {error_ctx} — returning None (must be handled by caller)")
        else:
            logger.warning(f"Converting None to {default} {error_ctx}—explicitly requested default")
        return default

    if isinstance(value, bool):
        if strict:
            raise StrictValidationError(f"Cannot convert bool to int {error_ctx}")
        return default

    try:
        return int(value)
    except (ValueError, TypeError) as e:
        if strict:
            raise StrictValidationError(
                f"Cannot convert {field_name or 'value'}={value!r} to int {error_ctx}: {e}"
            ) from e
        if default is None:
            logger.warning(
                f"Failed to convert {value!r} to int {error_ctx} (returning None—caller must handle missing data): {e}"
            )
        else:
            logger.warning(f"Failed to convert {value!r} to int {error_ctx} (returning {default}): {e}")
        return default


# ──────────────────────────────────────────────────────────────────────────────
# JSON PARSING
# ──────────────────────────────────────────────────────────────────────────────


def safe_json_parse(
    value: Any,
    default: Any = None,
    *,
    context: str = "",
    strict: bool = False,
    field_name: str | None = None,
) -> Any:
    """Parse JSON string with configurable failure behavior.

    Args:
        value: Value to parse (string, dict, list, or None)
        default: Value to return on parse failure (None requires caller to handle missing data)
        context: Context string for logging (deprecated, use field_name)
        strict: If True, raise StrictValidationError instead of returning default (REQUIRED for finance)
        field_name: Field name for error logging

    Returns:
        Parsed object, or default value, or raises StrictValidationError (if strict=True)

    Raises:
        StrictValidationError: If strict=True and parsing fails (no fallback to empty dict)
    """
    if value is None:
        if strict:
            raise StrictValidationError(f"Cannot parse None as JSON {field_name or context}")
        if default is None:
            logger.warning(f"None value in JSON parse {field_name or context} — returning None (caller must handle)")
        return default

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
                    f"Cannot parse JSON {field_name or context}: {e}. Value: {value[:100]}"
                ) from e
            logger.warning(
                f"Failed to parse JSON {field_name or context}: {e}. Value: {value[:100]} (returning {default!r})"
            )
            return default

    # For unexpected types
    if strict:
        raise StrictValidationError(
            f"Expected string or dict {field_name or context}, got {type(value).__name__}: {value!r}"
        )
    logger.warning(
        f"Expected string or dict {field_name or context}, got {type(value).__name__}: {value!r} (returning {default!r})"
    )
    return default


def safe_json_parse_strict(value: Any, context: str = "", field_name: str | None = None) -> Any:
    """Parse JSON in strict mode. Raises StrictValidationError if fails.

    REQUIRED for finance paths: No silent fallbacks or secondary sources.
    Explicitly validates JSON without empty dict defaults.

    Args:
        value: JSON string, dict, list, or None
        context: Context string for error messages
        field_name: Field name for error messages (preferred over context)

    Returns:
        Parsed object (never returns empty dict fallback)

    Raises:
        StrictValidationError: If value cannot be parsed as JSON
    """
    return safe_json_parse(value, default=None, context=context, strict=True, field_name=field_name)


# ──────────────────────────────────────────────────────────────────────────────
# BOOL CONVERSION
# ──────────────────────────────────────────────────────────────────────────────


def safe_bool(value: Any, default: bool | None = None, field_name: str | None = None) -> bool | None:
    """Safely convert value to bool with explicit failure handling.

    Args:
        value: Value to convert (bool, str, int, etc.)
        default: Default value if conversion fails (None requires caller to handle; use False for permissive)
        field_name: Field name for error logging

    Returns:
        bool value or default if conversion fails. Never silently defaults to False.
        If default is None and conversion fails, returns None (caller must handle).
    """
    if value is None:
        if default is None:
            logger.warning(f"None value in bool conversion {field_name or ''} — returning None (caller must handle)")
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        val_lower = value.lower().strip()
        if val_lower in ("true", "1", "yes", "on"):
            return True
        elif val_lower in ("false", "0", "no", "off", ""):
            return False
        else:
            if field_name:
                logger.warning(f"Cannot convert {field_name}={value!r} to bool (returning {default!r})")
            else:
                logger.warning(f"Cannot convert {value!r} to bool (returning {default!r})")
            return default

    try:
        return bool(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to bool (returning {default!r}): {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to bool (returning {default!r}): {e}")
        return default


# ──────────────────────────────────────────────────────────────────────────────
# STRING CONVERSION
# ──────────────────────────────────────────────────────────────────────────────


def safe_str(value: Any, default: str | None = None, field_name: str | None = None) -> str | None:
    """Safely convert value to string with explicit failure handling.

    Args:
        value: Value to convert
        default: Default value if conversion fails (None requires caller to handle missing data)
        field_name: Field name for error logging

    Returns:
        str value or default if conversion fails. NEVER silently defaults to empty string.
        If default is None and value is None, returns None (caller must handle).

    Raises:
        Never raises; returns default instead. Use strict mode in calling code for fail-fast.
    """
    if value is None:
        if default is None:
            logger.warning(f"None value in string conversion {field_name or ''} — returning None (caller must handle)")
        return default

    if isinstance(value, str):
        return value

    try:
        return str(value)
    except Exception as e:
        if field_name:
            logger.warning(f"Failed to convert {field_name}={value!r} to str (returning {default!r}): {e}")
        else:
            logger.warning(f"Failed to convert {value!r} to str (returning {default!r}): {e}")
        return default


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


def safe_json_get(obj: Any, key: str, default: Any = None, context: str = "") -> Any:
    """Safely get value from dict/object, logging on failure.

    Args:
        obj: Dictionary or object to read from
        key: Key to read
        default: Default if key missing or obj is invalid (None requires caller to handle missing data)
        context: Context string for logging

    Returns:
        Value at obj[key] or default. No secondary fallbacks — returns explicit default only.
    """
    if not isinstance(obj, dict):
        if default is None:
            logger.warning(f"Cannot read {key}: obj is {type(obj).__name__}, not dict {context} — returning None")
        return default

    if key not in obj:
        if default is None:
            logger.warning(f"Key {key!r} missing from dict {context} — returning None (caller must handle)")
        return default

    value = obj[key]
    if value is None and default is not None:
        logger.debug(f"Key {key!r} has None value {context} — returning default {default!r}")
        return default

    return value


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
            f"[{table_name}] No new rows inserted ({rows_skipped} skipped, {rows_failed} failed){duration_str}"
        )
    else:
        logger.info(f"[{table_name}] Loaded {rows_inserted}/{total} rows ({rows_skipped} skipped){duration_str}")
