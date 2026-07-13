"""Shared route utilities."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any, NoReturn, ParamSpec, TypeVar, cast

import psycopg2
import psycopg2.errors
import setup_imports  # noqa: F401
from exceptions import (
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


def normalize_to_utc_datetime(dt: date | datetime | None) -> dict[str, Any] | datetime:
    """Convert date or naive/aware datetime to UTC-aware datetime.

    Handles three cases:
    - date: converted to datetime at 00:00 UTC
    - naive datetime: assumed to be UTC, tzinfo added
    - aware datetime: returned as-is
    - None: returns explicit unavailability marker

    Args:
            dt: datetime, date, or None

    Returns:
            UTC-aware datetime or {"data_unavailable": True, "reason": "input_is_none"}
    """
    if dt is None:
        return {"data_unavailable": True, "reason": "input_is_none"}

    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

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
    from typing import cast

    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(int, ParamValidator.int(int_str, min_val=min_val, max_val=max_val))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_float(float_str: str | None, min_val: float | None = None, max_val: float | None = None) -> float:
    """DEPRECATED: Use ParamValidator.float() instead. Thin wrapper for backward compatibility."""
    from typing import cast

    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(float, ParamValidator.float(float_str, min_val=min_val, max_val=max_val))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_string(value_str: str | None, allowed_values: set[str] | None = None, max_length: int = 100) -> str:
    """DEPRECATED: Use ParamValidator.string() instead. Thin wrapper for backward compatibility."""
    from typing import cast

    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(str, ParamValidator.string(value_str, allowed_values=allowed_values, max_length=max_length))
    except ParamValidationError as e:
        raise_api_error(e.status_code, e.error_type, e.message)


def safe_symbol(symbol_str: str | None) -> str:
    """DEPRECATED: Use ParamValidator.symbol() instead. Thin wrapper for backward compatibility."""
    from typing import cast

    from routes.param_validators import ParamValidationError, ParamValidator

    try:
        return cast(str, ParamValidator.symbol(symbol_str))
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
        BadRequest: If required parameter is missing or empty and required is True
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
                try:
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
                except Exception:
                    # If column name extraction fails, return as-is
                    pass

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
    # Fallback — this should not happen
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
        from api_utils.config import get_config

        try:
            config = get_config()
            if config.data_freshness_max_hours is None:
                raise ValueError("data_freshness_max_hours is None in config")
            warning_days = max(1, int(config.data_freshness_max_hours / 24))
            logger.debug(f"[DATA_FRESHNESS] Using config default: {config.data_freshness_max_hours}h → {warning_days}d")
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

        # Financial market data only updates on trading days (Mon-Fri).
        # Adjust the staleness threshold so Friday's data stays "fresh" through
        # the weekend and into Monday morning (before EOD loaders run).
        weekday = today.weekday()  # 0=Mon … 6=Sun
        if weekday == 5:  # Saturday: Friday data is 1 day old → +1
            effective_warning = warning_days + 1
        elif weekday == 6:  # Sunday:   Friday data is 2 days old → +2
            effective_warning = warning_days + 2
        elif weekday == 0:  # Monday:   Friday data is 3 days old → +2
            effective_warning = warning_days + 2
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
        # Return safe default instead of failing the entire endpoint
        # Freshness check is non-critical and should not break API responses
        logger.warning(
            f"[DATA_FRESHNESS] Could not check freshness for {table_name}: {type(e).__name__}: {e}. Using safe default."
        )
        return {
            "data_age_days": None,
            "is_stale": False,
            "warning": None,
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
    """
    # Extract raw cursor if wrapped in DatabaseQueryService
    if hasattr(cursor_or_service, "cursor") and hasattr(cursor_or_service.cursor, "description"):
        # This is likely a DatabaseQueryService wrapping a cursor
        _thread_local.cursor = cursor_or_service.cursor
    else:
        # Use as-is (assume it's a raw cursor)
        _thread_local.cursor = cursor_or_service


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
        raise ValueError("Database row is None — cannot convert None to dict")

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

    # Use centralized classification (handles both psycopg2 and custom exceptions)
    # If classification fails, raise to alert ops — don't fall back to generic status
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
                # ResponseValidator not available (should not happen in Lambda)
                logger.warning(f"[VALIDATION] ResponseValidator not available: {e} - skipping validation")
                return response
            except Exception as e:
                # Validation itself failed (shouldn't happen, but don't break the API)
                logger.error(f"[VALIDATION] Validation check crashed for {endpoint_name}: {e}")
                return response

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
