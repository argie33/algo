"""Shared route utilities."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from functools import wraps
from typing import TYPE_CHECKING, Any, NoReturn, ParamSpec, TypeVar, cast

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo

import psycopg2
import psycopg2.errors
import setup_imports  # noqa: F401
from exceptions import (
    APIException,
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    QueryTimeout,
    ServiceUnavailable,
    TooManyRequests,
    UnprocessableEntity,
)
from psycopg2.extensions import cursor

from utils.validation import APIResponseValidator

logger = logging.getLogger(__name__)

# Thread-local storage for current cursor (used by safe_dict_convert to convert tuples)
_thread_local = threading.local()

# Type variables for decorators to preserve function signatures
P = ParamSpec("P")
R = TypeVar("R")

# Centralized query timeout configuration (milliseconds)
# Values chosen based on expected query complexity and business impact
QUERY_TIMEOUTS = {
    "default": 5000,  # Standard list/filter queries
    "count": 3000,  # COUNT(*) queries (fast)
    "complex_join": 8000,  # Multi-table joins
    "analytical": 15000,  # Analytical/aggregation queries
    "list": 5000,  # Paginated list queries
}


def set_query_timeout(cur: Any, timeout_ms: int | None = None, timeout_name: str = "default") -> None:
    """Set statement timeout for the current transaction.

    Args:
        cur: Database cursor
        timeout_ms: Explicit timeout in milliseconds (overrides timeout_name)
        timeout_name: Named timeout from QUERY_TIMEOUTS (default, count, complex_join, etc.)

    Raises:
        ValueError: If timeout_ms is invalid or timeout_name not found in QUERY_TIMEOUTS
    """
    # EXPLICIT: Only use named timeout if timeout_ms is None
    if timeout_ms is None:
        # SAFETY: Fail fast if timeout_name not found (don't silently use default)
        if timeout_name not in QUERY_TIMEOUTS:
            raise ValueError(
                f"Unknown timeout_name '{timeout_name}'. Must be one of: {', '.join(QUERY_TIMEOUTS.keys())}"
            )
        timeout_ms = QUERY_TIMEOUTS[timeout_name]
        logger.debug(f"[QUERY_TIMEOUT] Using named timeout '{timeout_name}': {timeout_ms}ms")

    # Validate timeout_ms is an integer to prevent injection
    if not isinstance(timeout_ms, int) or timeout_ms < 0:
        raise ValueError(f"Invalid timeout_ms: must be non-negative integer, got {timeout_ms}")
    cur.execute(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")


def normalize_to_utc_datetime(
    dt: date | datetime | None, naive_tz: ZoneInfo | None = None
) -> dict[str, Any] | datetime:
    """Convert date or naive/aware datetime to UTC-aware datetime.

    Handles three cases:
    - date: converted to datetime at 00:00 UTC
    - naive datetime: interpreted per `naive_tz` (see below), tzinfo added
    - aware datetime: returned as-is
    - None: returns explicit unavailability marker

    Args:
            dt: datetime, date, or None
            naive_tz: timezone a naive `dt` should be interpreted in before converting to
                UTC. Naive timestamp columns in this codebase are written by
                utils/bulk_insert_manager.py's session-local convention (`SHOW timezone`,
                not UTC - see that module's docstring: COPY into a `timestamp without time
                zone` column silently drops any UTC offset, so tz-aware datetimes are
                converted to the session's wall-clock before insert). Treating a naive
                value as UTC when it's actually e.g. America/Chicago silently inflates any
                "age" computed against it by the zone's UTC offset (4-6h) - confirmed live
                for data_loader_status.last_updated via /api/algo/data-status, which showed
                age_hours=5.2 for a table updated 9 minutes earlier. Pass the DB session's
                actual timezone (`SHOW timezone`, resolved once by the caller - not per
                call, to avoid re-querying it for every row) whenever the source column
                follows that convention; omit to keep the old UTC-assumed default.

    Returns:
            UTC-aware datetime or {"data_unavailable": True, "reason": "input_is_none"}
    """
    if dt is None:
        return {"data_unavailable": True, "reason": "input_is_none"}

    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=naive_tz or timezone.utc)
        return dt.astimezone(timezone.utc)

    return {"data_unavailable": True, "reason": f"invalid_type_{type(dt).__name__}"}


def safe_limit(limit_str: str | None, max_val: int = 5000, default: int | None = None) -> int:
    """DEPRECATED: Use ParamValidator.limit() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(int, ParamValidator.limit(limit_str, max_val=max_val, default=default))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_offset(offset_str: str | None, max_val: int = 1000000) -> int:
    """DEPRECATED: Use ParamValidator.offset() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(int, ParamValidator.offset(offset_str, max_val=max_val))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_days(days_str: str | None, max_val: int = 365, default: int | None = None) -> int:
    """DEPRECATED: Use ParamValidator.days() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(int, ParamValidator.days(days_str, max_val=max_val, default=default))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_page(page_str: str | None, default: int | None = None) -> int:
    """DEPRECATED: Use ParamValidator.page() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(int, ParamValidator.page(page_str, default=default))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_int(int_str: str | None, min_val: int | None = None, max_val: int | None = None) -> int:
    """DEPRECATED: Use ParamValidator.int() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return ParamValidator.int(int_str, min_val=min_val, max_val=max_val)
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_float(float_str: str | None, min_val: float | None = None, max_val: float | None = None) -> float:
    """DEPRECATED: Use ParamValidator.float() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return ParamValidator.float(float_str, min_val=min_val, max_val=max_val)
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_string(value_str: str | None, allowed_values: set[str] | None = None, max_length: int = 100) -> str:
    """DEPRECATED: Use ParamValidator.string() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return ParamValidator.string(value_str, allowed_values=allowed_values, max_length=max_length)
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_symbol(symbol_str: str | None) -> str:
    """DEPRECATED: Use ParamValidator.symbol() instead. Thin wrapper for backward compatibility."""
    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return ParamValidator.symbol(symbol_str)
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def get_api_version_headers() -> dict[str, str]:
    """Return API version header for all responses.

    Includes X-API-Version header so clients and monitoring systems can detect
    schema changes and breaking API modifications.

    Returns:
        Dict with X-API-Version header
    """
    from api_utils.config import API_VERSION, API_VERSION_HEADER

    return {API_VERSION_HEADER: API_VERSION}


def error_response(code: int, typ: str, msg: str | None) -> Any:
    """Standardized error response.

    Returns consistent error format with statusCode, errorType, message, and _error.
    All error responses include HTTP status code for client-side error handling.
    The _error field enables consistent error detection across the dashboard.

    For 503/504 errors, marks them as transient so dashboard fetchers retry with backoff.
    Both indicate temporary service issues (503=overloaded, 504=slow query) that usually recover.

    DEPRECATED: Prefer raising APIException subclasses instead.
    Use raise_api_error() or raise_db_error() helper functions.
    """
    # Sanitize message to remove credentials, paths, SQL
    from utils.error_handlers import sanitize_error_message

    # HIGH-005 FIX: Require message, don't silently replace None with empty string
    if msg is None:
        logger.error(f"[error_response] message is None for code {code}, typ={typ}")
        msg = f"Error {typ} ({code})"

    msg = sanitize_error_message(msg)

    response = cast(dict[str, Any], {"statusCode": code, "errorType": typ, "message": msg, "_error": msg})
    # Mark 503/504 errors as transient so dashboard fetchers retry with exponential backoff
    # Dashboard retry logic depends on these markers to distinguish transient vs permanent failures
    if code == 503:
        response["_is_transient_503"] = True
    elif code == 504:
        response["_is_transient_504"] = True
    return response


def no_data_response(msg: str | None = None) -> Any:
    """Standardized response for empty query results.

    CRITICAL FIX: Distinguish "query executed successfully but returned 0 rows" (no_data)
    from "query execution failed" (query_failed). This allows callers to distinguish:
    - No data (200): Query succeeded, zero rows returned (expected for some endpoints)
    - Query failed (500): Database error, network issue, etc. (needs investigation)

    Args:
        msg: Optional message explaining why no data (e.g., "No data for this date range")

    Returns:
        Response dict with statusCode 200 and errorType "no_data"
    """
    from utils.error_handlers import sanitize_error_message

    if msg is None:
        msg = "No data found for the requested query"
    msg = sanitize_error_message(msg)

    return cast(
        dict[str, Any],
        {"statusCode": 200, "errorType": "no_data", "message": msg, "_error": msg, "_is_no_data": True},
    )


def query_failed_response(error: Exception | str, context: str = "query") -> Any:
    """Standardized response for query execution failures.

    CRITICAL FIX: Distinguish "query executed but returned no rows" (no_data)
    from "query execution failed" (query_failed). This makes errors actionable:
    - Query failed (500): Database connection, parse error, timeout → needs ops attention
    - No data (200): Empty result set → expected behavior for some endpoints

    Args:
        error: Exception or error message
        context: Operation context for logging

    Returns:
        Response dict with statusCode 500 and errorType "query_failed"
    """
    from utils.error_handlers import sanitize_error_message

    error_msg = str(error) if isinstance(error, Exception) else str(error)
    error_msg = sanitize_error_message(error_msg)

    logger.error(f"[query_failed_response] {context} failed: {error_msg}")

    return cast(
        dict[str, Any],
        {"statusCode": 500, "errorType": "query_failed", "message": error_msg, "_error": error_msg},
    )


def raise_db_error(error: Exception, context: str = "database operation") -> NoReturn:
    """Convert database error to APIException.

    Maps psycopg2 exceptions to appropriate HTTP status codes:
    - QueryCanceled → 504 QueryTimeout
    - UndefinedTable/UndefinedColumn → 503 ServiceUnavailable (schema error)
    - OperationalError/DatabaseError → 503 ServiceUnavailable (connection/query error)
    - Generic Exception → 500 ServiceUnavailable

    Args:
        error: Exception caught from database operation
        context: Operation name for logging context

    Raises:
        APIException: Appropriate exception type with status code
    """
    from utils.error_handlers import classify_exception, log_sanitizer

    # Already a well-formed API error (e.g. raised via raise_api_error() from inside the
    # same try block this was caught in) - re-raise as-is instead of collapsing every
    # non-504 status to a generic 503. This was previously unconditional: a deliberate
    # 400/403/404/409 raised anywhere inside a handler wrapped in a broad `except
    # Exception: raise_db_error(...)` always came back to the client as 503
    # ServiceUnavailable, discarding the real status code and message.
    if isinstance(error, APIException):
        with log_sanitizer(f"database error: {context}") as safe_log:
            safe_log.error(error)
        raise error

    # Use centralized classification to determine status code and error type
    try:
        status_code, _, message = classify_exception(error)
    except (psycopg2.DatabaseError, psycopg2.OperationalError):
        status_code = 503
        message = f"Error during {context}"

    # Log with sanitization to prevent PII/SQL leakage
    with log_sanitizer(f"database error: {context}") as safe_log:
        safe_log.error(error)

    # Raise appropriate exception based on status code
    if status_code == 504:
        raise QueryTimeout(message)
    else:
        raise ServiceUnavailable(message)


def extract_param(
    params: dict[str, Any] | None, key: str, required: bool = False, default: str | None = None
) -> str | None:
    """Extract parameter from CGI-style params dict (dict of lists).

    Args:
        params: Query parameters as dict of lists (from urllib.parse.parse_qs)
        key: Parameter name to extract
        required: If True, raise error if parameter missing
        default: Default value if parameter missing and not required

    Returns:
        Parameter value (first element from list) or default

    Raises:
        BadRequest: If required parameter is missing or empty and required
    """
    # EXPLICIT: Check each condition separately for clarity
    if params is None:
        if required:
            raise_api_error(400, "BadRequest", f"Required parameter missing: {key} (params dict is None)")
        return default

    if key not in params:
        if required:
            raise_api_error(400, "BadRequest", f"Required parameter missing: {key}")
        return default

    if not params[key]:  # Empty list or None
        if required:
            raise_api_error(400, "BadRequest", f"Required parameter missing: {key} (list is empty)")
        return default

    # Extract value from list or use as-is
    value = params[key][0] if isinstance(params[key], list) else params[key]

    # EXPLICIT: Check if value is empty string (different from None)
    if not value:  # Empty string or None
        if required:
            raise_api_error(400, "BadRequest", f"Required parameter is empty: {key}")
        return default

    return cast(str | None, value)


def raise_api_error(status_code: int, error_type: str, message: str | None) -> NoReturn:
    """Raise APIException with explicit status code and error type.

    Selects the appropriate exception subclass based on status code.

    Args:
        status_code: HTTP status code (400, 403, 404, 409, 422, 429, 503, 504)
        error_type: Error type string for client
        message: Error message
    """
    # Map status codes to exception classes
    exception_map = {
        400: BadRequest,
        403: Forbidden,
        404: NotFound,
        409: Conflict,
        422: UnprocessableEntity,
        429: TooManyRequests,
        503: ServiceUnavailable,
        504: QueryTimeout,
    }

    exc_class = exception_map.get(status_code, ServiceUnavailable)
    raise exc_class(message or "", error_type=error_type, status_code=status_code)


def success_response(data: dict[str, Any], metadata: dict[str, Any] | None = None) -> Any:
    """Standardized success response for single object.

    Always returns object with statusCode=200 and data field.
    Sanitizes response to remove None values (Issue #14 FIX).
    Optionally includes additional metadata (freshness, etc).
    """
    sanitized_data = APIResponseValidator.sanitize_response(data)
    response = {"statusCode": 200, "data": sanitized_data}
    if metadata:
        response.update(metadata)
    return response


def list_response(
    items: list[Any],
    total: int | None = None,
    data_freshness: dict[str, Any] | None = None,
    limit: int | None = None,
    offset: int | None = None,
    preserve_items: bool = False,
) -> Any:
    """Standardized list response for paginated data.

    Always returns array in 'data.items' field with total count.
    Sanitizes response to remove None values (Issue #14 FIX).
    Includes pagination metadata for client-side pagination.
    Format: {statusCode: 200, data: {items: [...], total: X, limit?: Y, offset?: Z}, data_freshness?: {...}}

    CRITICAL: preserve_items=True prevents sanitizing individual item dicts.
    Array items must preserve all fields (including None) for consistent schema.
    e.g., growth_score field must be present in all stocks even if None.
    """
    # EXPLICIT: Sanitize items; if None, use empty list (INTENT: no data, not missing)
    # CRITICAL FIX: Don't sanitize item dicts if preserve_items=True (maintain consistent schema per item)
    if preserve_items:
        sanitized_items = items if items is not None else []
    else:
        sanitized_items = APIResponseValidator.sanitize_response(items if items is not None else [])

    # EXPLICIT: If total not provided, use len(items); otherwise trust provided total
    total_count = total if total is not None else len(sanitized_items)

    data = {
        "items": sanitized_items,
        "total": total_count,
    }

    # EXPLICIT: Only include pagination fields if explicitly provided
    if limit is not None:
        data["limit"] = limit
    if offset is not None:
        data["offset"] = offset

    response = {"statusCode": 200, "data": data}

    # EXPLICIT: Only include data_freshness if explicitly provided and not empty
    if data_freshness is not None:
        response["data_freshness"] = data_freshness

    return response


def execute_with_timeout(
    cur: cursor,
    query: str,
    params: Any = None,
    timeout_sec: int = 10,
    max_attempts: int = 2,
    backoff_multiplier: float = 1.5,
) -> list[Any]:
    """Execute query with automatic timeout handling and exponential backoff retry.

    ALL database queries should use this wrapper to prevent hanging queries.

    Args:
        cur: Database cursor
        query: SQL query to execute
        params: Query parameters (for parameterized queries)
        timeout_sec: Initial timeout in seconds (default 10s)
        max_attempts: Number of retry attempts on timeout (default 2 = 1 retry)
        backoff_multiplier: Timeout multiplier on retry (default 1.5)

    Returns:
        Query result (list of rows) on success

    Raises:
        psycopg2.errors.QueryCanceled: If query times out after all retries
        Exception: For other database errors
    """
    from utils.error_handlers import log_sanitizer

    if not isinstance(timeout_sec, (int, float)):
        raise TypeError(f"timeout_sec must be numeric, got {type(timeout_sec).__name__}")
    current_timeout: float = float(timeout_sec)
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            # Set LOCAL timeout (connection-scoped, not global)
            timeout_ms = int(current_timeout * 1000)
            if timeout_ms < 0:
                raise ValueError(f"Invalid timeout: {timeout_ms}ms must be non-negative")
            cur.execute(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)

            # Fetch results and normalize to handle both DictCursor and tuple cursor results
            rows = cur.fetchall()

            # Convert tuple results to dicts using column names for consistency
            # This ensures routes can always access rows as dicts regardless of cursor type
            if rows and isinstance(rows[0], tuple) and cur.description:
                # Try to extract column names from description
                col_names = []
                for desc in cur.description:
                    try:
                        # Handle both subscriptable tuples and non-subscriptable objects
                        col_names.append(desc[0])
                    except (TypeError, IndexError):
                        # If desc is not subscriptable, try to get name attribute
                        if hasattr(desc, "name"):
                            col_names.append(desc.name)
                        else:
                            col_names.append(f"col_{len(col_names)}")

                if col_names:
                    return [dict(zip(col_names, row, strict=True)) for row in rows]
                else:
                    raise RuntimeError(
                        "Failed to extract column names from cursor description. "
                        "Cannot convert tuple results to dicts."
                    )

            return list(rows)

        except psycopg2.errors.QueryCanceled as e:
            last_error = e
            if attempt < max_attempts - 1:
                current_timeout *= backoff_multiplier
                with log_sanitizer("query timeout retry") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except (
                    psycopg2.DatabaseError,
                    psycopg2.OperationalError,
                ) as rollback_err:
                    logger.debug(f"Failed to rollback after query timeout: {rollback_err}")
                time.sleep(0.1)
            else:
                with log_sanitizer("query timeout final") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except (
                    psycopg2.DatabaseError,
                    psycopg2.OperationalError,
                ) as rollback_err:
                    logger.debug(f"Failed to rollback after final timeout: {rollback_err}")
                raise e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            last_error = e
            with log_sanitizer("query execution") as safe_log:
                safe_log.error(e)
            try:
                cur.connection.rollback()
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
                logger.debug(f"Failed to rollback after query error: {rollback_err}")
            # Re-raise so routes can handle database errors properly
            raise e

    # This line should never be reached, but kept for safety
    if last_error:
        with log_sanitizer("query execution final") as safe_log:
            safe_log.error(last_error)
        raise last_error
    # Fallback - this should not happen
    raise RuntimeError("Query execution failed without error")


def check_data_freshness(
    cur: cursor, table_name: str, date_column: str = "date", warning_days: int | None = None
) -> Any:
    """Check how fresh data is in a table.

    Args:
        cur: Database cursor or DatabaseQueryService wrapper
        table_name: Table to check
        date_column: Column containing date/timestamp (default "date")
        warning_days: Days beyond which data is considered stale.
                     If None, uses DATA_FRESHNESS_MAX_HOURS from config (converted to days).

    Returns:
        Dict with data_age_days, is_stale, max_date, warning

    Raises:
        ValueError: If warning_days calculation fails or config unavailable
    """
    # Extract raw cursor if wrapped in DatabaseQueryService
    if hasattr(cur, "cursor") and hasattr(cur.cursor, "execute"):
        cur = cur.cursor

    if warning_days is None:
        # NOTE: api_utils.config import works at runtime because Lambda packages this with
        # lambda/api/ in PYTHONPATH. Linter may flag as unresolved but it's correct.
        from api_utils.config import get_config

        try:
            config = get_config()
            if config.data_freshness_max_hours is None:
                raise ValueError("data_freshness_max_hours is None in config")
            warning_days = max(1, int(config.data_freshness_max_hours / 24))
            logger.debug(
                f"[DATA_FRESHNESS] Using config default: {config.data_freshness_max_hours}h -> {warning_days}d"
            )
        except (AttributeError, TypeError, ValueError) as e:
            logger.error(f"[DATA_FRESHNESS] Failed to load warning_days from config: {e}")
            raise ValueError(f"Cannot determine warning_days threshold: {e}") from e
    else:
        # EXPLICIT: Validate provided warning_days
        if warning_days < 0:
            raise ValueError(f"warning_days must be non-negative, got {warning_days}")

    try:
        import psycopg2.sql

        cur.execute(
            psycopg2.sql.SQL("SELECT MAX({}) as max_value FROM {}").format(
                psycopg2.sql.Identifier(date_column),
                psycopg2.sql.Identifier(table_name),
            )
        )
        result = cur.fetchone()

        # EXPLICIT: Check if result is None or if max_date is not present/None
        if result is None:
            logger.warning(f"[DATA_FRESHNESS] Query returned None for {table_name}.{date_column}")
            return {
                "data_age_days": None,
                "is_stale": True,
                "warning": f"No data in {table_name}",
            }

        # Handle both dict-like results (DictCursor) and tuple results (regular cursor)
        if isinstance(result, dict):
            max_date_value = result.get("max_value")
        else:
            # For tuple results, the MAX() query returns a single column at index 0
            # Handle both subscriptable tuples and non-subscriptable objects (e.g., SQLAlchemy Composed)
            try:
                max_date_value = result[0] if result else None
            except (TypeError, KeyError):
                # If result is not subscriptable, try to get the first attribute or method
                # This handles SQLAlchemy Composed and other wrapped objects
                if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
                    max_date_value = next(iter(result), None)
                else:
                    max_date_value = None
        if max_date_value is None:
            logger.warning(f"[DATA_FRESHNESS] No rows in {table_name} (max({date_column}) is None)")
            return {
                "data_age_days": None,
                "is_stale": True,
                "warning": f"No data in {table_name}",
            }

        from datetime import date

        max_date = max_date_value

        # Handle both date and datetime objects
        if hasattr(max_date, "date"):
            max_date = max_date.date()

        today = date.today()
        data_age = (today - max_date).days

        # Financial market data only updates on trading days.
        # Calculate the most recent trading day and allow grace relative to that.
        # CRITICAL: Use MarketCalendar.is_trading_day() instead of hardcoded weekday checks
        # to handle market holidays (e.g., Presidents Day, Thanksgiving).
        # If today is a trading day: Friday data is 1 day old (if today is Monday) → +0 to +1 grace
        # If today is weekend/holiday: Friday data is N days old but M trading days old → use trading days
        from datetime import timedelta

        from algo.infrastructure import MarketCalendar

        # Find most recent trading day before or on today
        most_recent_trading_day = today
        for _ in range(10):
            if MarketCalendar.is_trading_day(most_recent_trading_day):
                break
            most_recent_trading_day -= timedelta(days=1)

        # If max_date is from the most recent trading day, data is fresh
        # Allow up to warning_days of staleness (e.g., +1 = data from yesterday trading day OK)
        if max_date >= most_recent_trading_day:
            effective_warning = warning_days
        else:
            # Data is from before most recent trading day - allow extra grace only if we're
            # in the pre-market hours before market opens (9:30 AM ET)
            from datetime import datetime
            from zoneinfo import ZoneInfo

            now_et = datetime.now(ZoneInfo("America/New_York"))
            if now_et.hour < 10:  # Pre-market (before 10 AM ET = safe pre-market window)
                effective_warning = warning_days + 1
            else:
                effective_warning = warning_days

        is_stale = data_age > effective_warning

        return {
            "data_age_days": data_age,
            "is_stale": is_stale,
            "max_date": str(max_date),
            "warning": f"Data is {data_age} days old" if is_stale else None,
        }
    except (
        psycopg2.DatabaseError,
        psycopg2.OperationalError,
        ValueError,
        ZeroDivisionError,
        TypeError,
        AttributeError,
        IndexError,
    ) as e:
        # CRITICAL: Freshness check failure must NOT be masked with is_stale=False
        # For finance apps, returning is_stale=False on error falsely indicates "data is fresh"
        # when we actually DON'T KNOW. This can lead to trading on stale data.
        # Instead: return is_stale=None to signal "freshness unknown" to consumer.
        logger.error(
            f"[DATA_FRESHNESS_CRITICAL] Could not check freshness for {table_name}: {type(e).__name__}: {e}. "
            f"Data freshness unknown - returning None to consumer to prevent false confidence in stale data."
        )
        return {
            "data_age_days": None,
            "is_stale": None,  # CRITICAL FIX: None means "unknown", NOT "fresh"
            "warning": "Data freshness check failed - treat data as potentially stale",
        }


def json_response(
    code: int, data: dict[str, Any], data_freshness: dict[str, Any] | None = None, preserve_arrays: bool = False
) -> Any:
    """Standardized JSON response wrapper for single objects.

    Returns consistent format:
    - Success (200): {statusCode: 200, data: {...}, data_freshness?: {...}}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "...", _error: "..."}

    Sanitizes all responses to prevent None values from reaching frontend (Issue #14).

    CRITICAL: preserve_arrays=True prevents sanitizing dicts inside arrays (e.g., stock items in "top" field).
    Array items must preserve all fields to maintain consistent schema per item for frontend.
    """
    if code == 200:
        # CRITICAL FIX: Don't sanitize array items - they need consistent schema
        # e.g., growth_score field must be present in all stocks even if None
        if preserve_arrays:
            response = {"statusCode": 200, "data": data}
        else:
            response = success_response(data)
        if data_freshness:
            response["data_freshness"] = data_freshness
        return response
    else:
        # For error responses, sanitize to prevent None values in nested fields
        # BUT only auto-populate _error from message if message was not None originally
        has_non_none_message = "message" in data and data.get("message") is not None
        sanitized_data = APIResponseValidator.sanitize_response(data)
        error_resp: dict[str, Any] = {"statusCode": code, **sanitized_data}
        if "_error" not in error_resp and has_non_none_message:
            error_resp["_error"] = sanitized_data["message"]
        return error_resp


def validate_dashboard_response(endpoint_name: str, response_data: dict[str, Any]) -> Any:
    """Validate API response against dashboard contract schema.

    Validates that responses match the contract defined in shared_contracts.
    Logs validation errors for debugging but does NOT fail the request.
    This ensures the dashboard has predictable response schemas.

    Args:
        endpoint_name: Name of endpoint from DASHBOARD_ENDPOINTS (e.g., 'run', 'port', 'mkt')
        response_data: Response dict to validate (the 'data' field for JSON responses)

    Returns:
        The original response_data unchanged (validation is logging only)
    """
    try:
        from shared_contracts.response_validator import ResponseValidator

        is_valid, error_msg = ResponseValidator.validate_endpoint_response(endpoint_name, response_data)
        if not is_valid:
            logger.warning(
                f"[SCHEMA_VALIDATION] Endpoint '{endpoint_name}' response does not match contract: {error_msg}"
            )
    except (ImportError, AttributeError, KeyError, TypeError) as e:
        logger.warning(f"[SCHEMA_VALIDATION] Could not validate endpoint '{endpoint_name}': {type(e).__name__}: {e}")
    return response_data


def ensure_valid_response(endpoint_name: str, response_data: dict[str, Any]) -> bool:
    """Validate API response against dashboard contract schema.

    Returns True if response is valid, False otherwise. Logs validation errors.
    Use this to validate responses before returning them to the dashboard.

    Args:
        endpoint_name: Name of endpoint from DASHBOARD_ENDPOINTS (e.g., 'run', 'port', 'mkt')
        response_data: Response dict to validate (the 'data' field for JSON responses)

    Returns:
        True if valid, False if validation fails
    """
    try:
        from shared_contracts.response_validator import ResponseValidator

        is_valid, error_msg = ResponseValidator.validate_endpoint_response(endpoint_name, response_data)
        if not is_valid:
            logger.warning(f"[RESPONSE_VALIDATION] Endpoint '{endpoint_name}' validation failed: {error_msg}")
        return bool(is_valid)
    except (ImportError, AttributeError, KeyError, TypeError) as e:
        logger.warning(f"[RESPONSE_VALIDATION] Could not validate endpoint '{endpoint_name}': {type(e).__name__}: {e}")
        return False


def set_current_cursor(cursor_or_service: Any) -> None:
    """Store cursor in thread-local for safe_dict_convert to use.

    Handles both raw psycopg2 cursors and DatabaseQueryService wrappers.
    Unwraps nested cursor wrappers (_ErrorLoggedCursor and _CorrelationIdCursor)
    to get the actual underlying psycopg2 cursor.
    """
    # Unwrap nested cursor wrappers to get the actual psycopg2 cursor
    # CRITICAL: bounded depth. Only 2 wrapper levels exist today (_ErrorLoggedCursor,
    # _CorrelationIdCursor), but `hasattr(x, "cursor")` never naturally terminates for
    # some objects (e.g. unittest.mock.MagicMock auto-creates any attribute, including
    # `.cursor` and `.description`, on every child it returns) - confirmed live via a
    # test using a bare MagicMock as a fake cursor, which hung the process indefinitely
    # walking `.cursor.cursor.cursor...` forever. A real malformed/self-wrapping wrapper
    # in production would hit the same failure mode. 10 iterations is generous headroom
    # over the 2 known levels.
    current = cursor_or_service
    for _ in range(10):
        if not hasattr(current, "cursor"):
            break
        # Keep unwrapping until we reach the actual psycopg2 cursor
        # (which has a description attribute but no nested cursor attribute)
        next_cursor = current.cursor
        if hasattr(next_cursor, "description"):
            current = next_cursor
        else:
            break
    else:
        logger.error(
            f"[set_current_cursor] Exceeded max unwrap depth (10) for {type(cursor_or_service).__name__}; "
            "possible self-referential or malformed cursor wrapper. Using last-unwrapped value."
        )

    _thread_local.cursor = current


def clear_current_cursor() -> None:
    """Clear thread-local cursor (call after request completes).

    CRITICAL FIX: In dev_server, threads are reused between requests.
    Without clearing, the old (closed) cursor stays in thread-local storage,
    causing safe_dict_convert to fail on subsequent requests using the same thread.

    In production Lambda, each request gets its own context, so this is less critical,
    but good practice to clean up regardless.
    """
    if hasattr(_thread_local, "cursor"):
        delattr(_thread_local, "cursor")


def safe_dict_convert(row: Any) -> Any:
    """Safely convert database row to dictionary, handling both DictCursor and tuple rows.

    Handles:
    - DictCursor rows: return as-is (already dict-like)
    - Tuple rows: convert using thread-local cursor.description
    - Dict-like objects: convert via dict()

    Args:
        row: Database row (dict-like or tuple)

    Returns:
        Dict of row data

    Raises:
        ValueError: If row is None
    """
    if row is None:
        raise ValueError("Database row is None - cannot convert None to dict")

    # If it's already a dict, return it
    if isinstance(row, dict):
        return row

    # For tuples, use thread-local cursor.description to get column names
    if isinstance(row, tuple):
        cursor = getattr(_thread_local, "cursor", None)
        if cursor is None or cursor.description is None:
            raise RuntimeError(
                f"Cannot convert tuple row to dict without cursor.description. "
                f"Cursor: {cursor}, Description: {cursor.description if cursor else 'None'}"
            )
        column_names = [desc[0] for desc in cursor.description]
        return dict(zip(column_names, row, strict=True))

    # Try to convert dict-like objects
    try:
        return dict(row)
    except (KeyError, ValueError, TypeError) as e:
        row_keys = list(row.keys()) if hasattr(row, "keys") else "unknown"
        raise RuntimeError(
            f"Failed to convert database row to dict: {type(e).__name__}: {e}\n"
            f"  Row keys: {row_keys}\n"
            f"  Row type: {type(row).__name__}"
        ) from e


def safe_json_serialize(obj: Any) -> Any:
    """Convert database objects to JSON-serializable format.

    Converts non-JSON types: Decimal→float, datetime/date→ISO string, UUID→string.
    Handles nested dicts and lists recursively.

    Args:
        obj: Dict, list, or scalar to convert

    Returns:
        Object with all non-JSON-serializable values converted
    """
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(obj, dict):
        return {k: safe_json_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [safe_json_serialize(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, UUID):
        return str(obj)
    else:
        return obj


def handle_db_error(
    error: Exception,
    context: str = "database operation",
    query: str | None = None,
    params: Any = None,
) -> tuple[int, str, str]:
    """Unified database error handler for all route handlers.

    Uses centralized error classification from utils.error_handlers.classify_exception.
    Logs with automatic PII/SQL sanitization via log_sanitizer context manager.

    Args:
        error: The exception caught
        context: Operation name for logging context (string, not logger instance)
        query: SQL query being executed (optional, for debugging)
        params: Query parameters (optional, for debugging)

    Returns:
        Tuple of (statusCode, errorType, message) for standardized error responses

    Raises:
        Exception: If error classification fails (fail-closed: don't guess error type)
    """
    from utils.error_handlers import classify_exception, log_sanitizer

    # A raise_api_error()/APIException instance (BadRequest, Forbidden, NotFound, etc.)
    # already carries the correct status_code/error_type/message. Route handlers often
    # raise these from inside their own try block (e.g. a validation failure detected
    # mid-query), so this function must preserve them rather than reclassifying via
    # classify_exception - that helper only knows utils.exceptions.core.BaseAPIError and
    # psycopg2 errors, a different hierarchy from lambda/api/exceptions.py's APIException,
    # so every deliberate 400/403/404/409 was silently collapsing to a generic 500.
    if isinstance(error, APIException):
        status_code, error_type, message = error.status_code, error.error_type, error.message
    else:
        # Use centralized classification (handles both psycopg2 and custom exceptions)
        # If classification fails, raise to alert ops - don't fall back to generic status
        status_code, error_type, message = classify_exception(error)

    # Log with sanitization to prevent PII/SQL leakage
    with log_sanitizer(f"database error: {context}") as safe_log:
        ctx_dict = {}
        if query:
            ctx_dict["query"] = query
        if params:
            ctx_dict["params"] = params
        safe_log.error(error, context=ctx_dict if ctx_dict else None)

    return status_code, error_type, message


def validate_api_response(endpoint_name: str) -> Callable[[Callable[P, dict[str, Any]]], Callable[P, dict[str, Any]]]:
    """Decorator: Validate API response matches contract schema before returning.

    Ensures all responses conform to the published dashboard API contract.
    If response doesn't match schema, returns explicit error instead of silent mismatch.

    Args:
        endpoint_name: Name of endpoint (e.g., 'cfg', 'run', 'port') from DASHBOARD_ENDPOINTS

    Example:
        @validate_api_response('cfg')  # type: ignore[untyped-decorator]
        def _get_algo_config(cur): ...

    CRITICAL: This decorator:
    - Validates successful responses against contract
    - Skips validation for error responses (they have their own format)
    - Raises explicit error if format mismatches (doesn't silently pass)
    - Logs the contract violation for debugging
    """

    def decorator(func: Callable[P, dict[str, Any]]) -> Callable[P, dict[str, Any]]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
            logger.debug(
                f"[VALIDATE_DECORATOR] validate_api_response('{endpoint_name}') decorator wrapping function {func.__name__}"
            )
            response = func(*args, **kwargs)
            logger.debug(
                f"[VALIDATE_DECORATOR] Function {func.__name__} returned: status={response.get('statusCode') if isinstance(response, dict) else 'N/A'}"
            )

            # Skip validation for error responses (400, 401, 403, 404, 500, 503)
            # Error responses have their own format and don't need contract validation
            if isinstance(response, dict) and response.get("statusCode") in (
                400,
                401,
                403,
                404,
                500,
                503,
            ):
                logger.debug(
                    f"[VALIDATION] Skipping validation for error response (statusCode={response.get('statusCode')})"
                )
                return response

            # Validate successful responses
            try:
                from shared_contracts.response_validator import ResponseValidator

                # Extract data to validate (could be in response["data"] or direct dict)
                data_to_validate = response.get("data", response) if isinstance(response, dict) else response

                is_valid, error_msg = ResponseValidator.validate_endpoint_response(endpoint_name, data_to_validate)

                if not is_valid:
                    logger.error(
                        f"[VALIDATION] Response format mismatch for {endpoint_name}: {error_msg}. "
                        f"API response doesn't match contract. Check that handler returns {endpoint_name} schema."
                    )
                    logger.debug(f"[VALIDATION] Response data: {data_to_validate}")

                    # Return explicit error (don't silently pass)
                    return cast(
                        dict[str, Any],
                        error_response(
                            500,
                            "response_validation_error",
                            f"API contract violation for {endpoint_name}: {error_msg}. "
                            "Check API logs for contract details.",
                        ),
                    )

                return response

            except ImportError as e:
                # ResponseValidator not available - this should not happen in Lambda, indicates a deployment issue
                raise RuntimeError(
                    f"ResponseValidator module not available (critical for response validation): {e}. "
                    "Check that shared_contracts module is deployed with Lambda."
                ) from e
            except Exception as e:
                # Validation itself failed - this is a programming error, not transient
                raise RuntimeError(
                    f"Response validation framework crashed for {endpoint_name}: {e}. "
                    "This indicates a bug in the validation logic, not a data issue."
                ) from e

        return wrapper

    return decorator


def db_route_handler(
    operation_name: str, default_error_response: Any = None
) -> Callable[[Callable[P, dict[str, Any]]], Callable[P, dict[str, Any]]]:
    """Decorator for route handlers to standardize database error handling.

    Eliminates redundant try-except blocks by wrapping function with:
    - Consistent database error catching
    - Unified error logging via handle_db_error() with PII/SQL sanitization
    - Standard error response formatting with _error field for consistency

    When database errors occur, returns proper error status codes (503, 504, etc.)
    instead of 200 OK with empty data. This prevents silent data failures that appear
    successful to clients but contain no data.

    Args:
        operation_name: Description of the operation for logging context
        default_error_response: DEPRECATED - ignored. Errors always return proper HTTP status.
                              This parameter is kept for backward compatibility.

    Example:
        @db_route_handler('fetch user data')  # type: ignore[untyped-decorator]
        def _get_users(cur): ...
    """

    def decorator(func: Callable[P, dict[str, Any]]) -> Callable[P, dict[str, Any]]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
            try:
                # Store cursor in thread-local for safe_dict_convert to access
                # First arg is always the cursor when decorated with @db_route_handler
                if args:
                    set_current_cursor(args[0])
                return func(*args, **kwargs)
            except (
                psycopg2.errors.UndefinedTable,
                psycopg2.errors.UndefinedColumn,
                psycopg2.OperationalError,
                psycopg2.DatabaseError,
                Exception,
            ) as e:
                code, error_type, message = handle_db_error(e, operation_name)
                # Always return proper error response with correct HTTP status code
                # Never return 200 OK with empty data - use proper 503/504/500 instead
                return cast(dict[str, Any], error_response(code, error_type, message))

        return wrapper

    return decorator
