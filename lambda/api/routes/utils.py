"""Shared route utilities."""

import logging
import re
import time
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any

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

from utils.validation import APIResponseValidator


logger = logging.getLogger(__name__)


def normalize_to_utc_datetime(dt):
    """Convert date or naive/aware datetime to UTC-aware datetime.

    Handles three cases:
    - date: converted to datetime at 00:00 UTC
    - naive datetime: assumed to be UTC, tzinfo added
    - aware datetime: returned as-is

    Args:
            dt: datetime, date, or None

    Returns:
            UTC-aware datetime or None
    """
    if dt is None:
        return None

    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, datetime.min.time())

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    return None


def safe_limit(limit_str, max_val=5000, default=500):
    """Parse and validate limit parameter."""
    if not limit_str:
        return default
    try:
        return min(int(limit_str), max_val)
    except (ValueError, TypeError):
        return default


def safe_offset(offset_str, max_val=1000000, default=0):
    """Parse and validate offset parameter."""
    if not offset_str:
        return default
    try:
        value = int(offset_str)
        return max(0, min(value, max_val))
    except (ValueError, TypeError):
        return default


def safe_days(days_str, max_val=365, default=30):
    """Parse and validate days parameter."""
    if not days_str:
        return default
    try:
        return max(1, min(int(days_str), max_val))
    except (ValueError, TypeError):
        return default


def safe_page(page_str, default=1):
    """Parse and validate page parameter."""
    if not page_str:
        return default
    try:
        return max(1, int(page_str))
    except (ValueError, TypeError):
        return default


def safe_int(int_str, default=0, min_val=None, max_val=None):
    """Parse and validate integer parameter."""
    if int_str is None or int_str == "":
        return default
    try:
        value = int(int_str)
        if min_val is not None:
            value = max(value, min_val)
        if max_val is not None:
            value = min(value, max_val)
        return value
    except (ValueError, TypeError):
        return default


def safe_float(float_str, default=0.0, min_val=None, max_val=None):
    """Parse and validate float parameter."""
    if float_str is None or float_str == "":
        return default
    try:
        value = float(float_str)
        if min_val is not None:
            value = max(value, min_val)
        if max_val is not None:
            value = min(value, max_val)
        return value
    except (ValueError, TypeError):
        return default


def safe_string(value_str, allowed_values=None, default=None, max_length=100):
    """Validate and sanitize string parameter.

    Args:
        value_str: String to validate
        allowed_values: Set of allowed values (whitelist)
        default: Default if invalid
        max_length: Maximum allowed length

    Returns:
        Validated string or default
    """
    if not value_str:
        return default

    # Enforce max length
    if len(str(value_str)) > max_length:
        return default

    # Check against whitelist if provided
    if allowed_values is not None:
        if str(value_str) not in allowed_values:
            return default

    return str(value_str)


def safe_symbol(symbol_str):
    """Validate stock symbol (alphanumeric + dash + caret for indices)."""
    if not symbol_str:
        return None

    # Allow up to 10 chars: alphanumeric, dash, caret (^GSPC, BRK-A, BRK.B)
    symbol = str(symbol_str).upper()
    if len(symbol) > 10:
        return None

    if not all(c.isalnum() or c in "-^." for c in symbol):
        return None

    return symbol


def error_response(code, typ, msg):
    """Standardized error response.

    Returns consistent error format with statusCode, errorType, message, and _error.
    All error responses include HTTP status code for client-side error handling.
    The _error field enables consistent error detection across the dashboard.

    DEPRECATED: Prefer raising APIException subclasses instead.
    Use raise_api_error() or raise_db_error() helper functions.
    """
    # Sanitize message to remove credentials, paths, SQL
    try:
        from utils.error_handlers import sanitize_error_message

        msg = sanitize_error_message(msg)
    except Exception:
        # Fallback: basic sanitization if import fails
        msg = re.sub(r"password=\S+|api.?key=\S+", "***", msg)

    return {"statusCode": code, "errorType": typ, "message": msg, "_error": msg}


def raise_db_error(error, context="database operation"):
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
    except Exception:
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


def raise_api_error(status_code, error_type, message):
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
    raise exc_class(message, error_type=error_type, status_code=status_code)


def success_response(data, metadata=None):
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


def list_response(items, total=None, data_freshness=None, limit=None, offset=None):
    """Standardized list response for paginated data.

    Always returns array in 'data.items' field with total count.
    Sanitizes response to remove None values (Issue #14 FIX).
    Includes pagination metadata for client-side pagination.
    Format: {statusCode: 200, data: {items: [...], total: X, limit?: Y, offset?: Z}, data_freshness?: {...}}
    """
    sanitized_items = APIResponseValidator.sanitize_response(items if items else [])
    data = {
        "items": sanitized_items,
        "total": total if total is not None else len(sanitized_items),
    }
    if limit is not None:
        data["limit"] = limit
    if offset is not None:
        data["offset"] = offset

    response = {"statusCode": 200, "data": data}
    if data_freshness:
        response["data_freshness"] = data_freshness
    return response


def execute_with_timeout(
    cur,
    query: str,
    params=None,
    timeout_sec: int = 10,
    max_attempts: int = 2,
    backoff_multiplier: float = 1.5,
):
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

    current_timeout = timeout_sec
    last_error = None

    for attempt in range(max_attempts):
        try:
            # Set LOCAL timeout (connection-scoped, not global)
            cur.execute(
                f"SET LOCAL statement_timeout = '{int(current_timeout * 1000)}ms'"
            )
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            return cur.fetchall()

        except psycopg2.errors.QueryCanceled as e:
            last_error = e
            if attempt < max_attempts - 1:
                current_timeout *= backoff_multiplier
                with log_sanitizer("query timeout retry") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except Exception as rollback_err:
                    logger.debug(
                        f"Failed to rollback after query timeout: {rollback_err}"
                    )
                time.sleep(0.1)
            else:
                with log_sanitizer("query timeout final") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except Exception as rollback_err:
                    logger.debug(f"Failed to rollback after final timeout: {rollback_err}")
                raise e
        except Exception as e:
            last_error = e
            with log_sanitizer("query execution") as safe_log:
                safe_log.error(e)
            try:
                cur.connection.rollback()
            except Exception as rollback_err:
                logger.debug(f"Failed to rollback after query error: {rollback_err}")
            # Re-raise so routes can handle database errors properly
            raise e

    # This line should never be reached, but kept for safety
    if last_error:
        with log_sanitizer("query execution final") as safe_log:
            safe_log.error(last_error)
        raise last_error


def check_data_freshness(
    cur, table_name: str, date_column: str = "date", warning_days: int | None = None
) -> dict:
    """Check how fresh data is in a table.

    Args:
        cur: Database cursor
        table_name: Table to check
        date_column: Column containing date/timestamp
        warning_days: Days beyond which data is considered stale.
                     If None, uses DATA_FRESHNESS_MAX_HOURS from config (converted to days).

    Returns:
        Dict with data_age_days, is_stale, max_date, warning
    """
    if warning_days is None:
        from api_utils.config import get_config

        config = get_config()
        warning_days = max(1, int(config.data_freshness_max_hours / 24))

    try:
        import psycopg2.sql

        cur.execute(
            psycopg2.sql.SQL("SELECT MAX({}) FROM {}").format(
                psycopg2.sql.Identifier(date_column),
                psycopg2.sql.Identifier(table_name),
            )
        )
        result = cur.fetchone()

        if not result or not result.get("max"):
            return {
                "data_age_days": None,
                "is_stale": True,
                "warning": f"No data in {table_name}",
            }

        from datetime import date

        max_date = result["max"]

        # Handle both date and datetime objects
        if hasattr(max_date, "date"):
            max_date = max_date.date()

        today = date.today()
        data_age = (today - max_date).days

        # Financial market data only updates on trading days (Mon-Fri).
        # Adjust the staleness threshold on weekends so Friday's data stays
        # "fresh" through Sunday without triggering false stale warnings.
        weekday = today.weekday()  # 0=Mon … 6=Sun
        if weekday == 5:  # Saturday: Friday data is 1 day old → +1
            effective_warning = warning_days + 1
        elif weekday == 6:  # Sunday:   Friday data is 2 days old → +2
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
    except Exception:
        # SECURITY FIX S-11: Don't expose database error details to client
        return {
            "data_age_days": None,
            "is_stale": True,
            "warning": "Unable to determine data freshness",
        }


def json_response(code, data, data_freshness=None):
    """Standardized JSON response wrapper for single objects.

    Returns consistent format:
    - Success (200): {statusCode: 200, data: {...}, data_freshness?: {...}}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "...", _error: "..."}

    Sanitizes all responses to prevent None values from reaching frontend (Issue #14).
    """
    if code == 200:
        response = success_response(data)
        if data_freshness:
            response["data_freshness"] = data_freshness
        return response
    else:
        # For error responses, sanitize to prevent None values in nested fields
        # BUT only auto-populate _error from message if message was not None originally
        has_non_none_message = "message" in data and data.get("message") is not None
        sanitized_data = APIResponseValidator.sanitize_response(data)
        response = {"statusCode": code, **sanitized_data}
        if "_error" not in response and has_non_none_message:
            response["_error"] = sanitized_data["message"]
        return response


def validate_dashboard_response(endpoint_name: str, response_data: dict[str, Any]) -> dict[str, Any]:
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
        is_valid, error_msg = ResponseValidator.validate_endpoint_response(
            endpoint_name, response_data
        )
        if not is_valid:
            logger.warning(
                f"[SCHEMA_VALIDATION] Endpoint '{endpoint_name}' response does not match contract: {error_msg}"
            )
    except Exception as e:
        logger.warning(
            f"[SCHEMA_VALIDATION] Could not validate endpoint '{endpoint_name}': {type(e).__name__}: {e}"
        )
    return response_data


def safe_dict_convert(row):
    """Safely convert DictCursor row to dictionary, handling schema mismatches.

    DictCursor rows support dict() conversion, but this can fail if:
    - Database schema has changed (missing/extra columns)
    - Column names don't exist in the row
    - Row is None or invalid

    Args:
        row: DictCursor row from database query, or None

    Returns:
        Dict of row data, or empty dict if conversion fails.
        Logs KeyError/ValueError for debugging schema issues.
    """
    if row is None:
        return {}

    try:
        return dict(row)
    except (KeyError, ValueError, TypeError) as e:
        row_keys = list(row.keys()) if hasattr(row, "keys") else "unknown"
        logger.error(
            f"Failed to convert row to dict: {type(e).__name__}: {e}\n  Row keys: {row_keys}\n  Row type: {type(row).__name__}\n  Context: DictCursor row conversion (possible schema mismatch)"
        )
        try:
            if hasattr(row, "keys"):
                return {k: row[k] for k in row.keys() if k is not None}
        except Exception as fallback_err:
            logger.error(f"Fallback dict conversion also failed: {fallback_err}")
        return {}


def safe_json_serialize(obj):
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


def handle_db_error(error, context="database operation", query=None, params=None):
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
    """
    from utils.error_handlers import classify_exception, log_sanitizer

    # Use centralized classification (handles both psycopg2 and custom exceptions)
    try:
        status_code, error_type, message = classify_exception(error)
    except Exception:
        # Fallback to old logic if import fails
        status_code = 500
        error_type = "database_error"
        message = f"Error during {context}"

    # Log with sanitization to prevent PII/SQL leakage
    with log_sanitizer(f"database error: {context}") as safe_log:
        ctx_dict = {}
        if query:
            ctx_dict["query"] = query
        if params:
            ctx_dict["params"] = params
        safe_log.error(error, context=ctx_dict if ctx_dict else None)

    return status_code, error_type, message


def db_route_handler(operation_name: str, default_error_response=None):
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
        @db_route_handler('fetch user data')
        def _get_users(cur): ...
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
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
                return json_response(
                    code,
                    {"errorType": error_type, "message": message, "_error": message},
                )

        return wrapper

    return decorator
