"""Shared route utilities."""

import logging
import time
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any, NoReturn

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
    """
    if timeout_ms is None:
        timeout_ms = QUERY_TIMEOUTS.get(timeout_name, QUERY_TIMEOUTS["default"])
    # Validate timeout_ms is an integer to prevent injection
    if not isinstance(timeout_ms, int) or timeout_ms < 0:
        raise ValueError(f"Invalid timeout_ms: must be non-negative integer, got {timeout_ms}")
    cur.execute(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")


def normalize_to_utc_datetime(dt: date | datetime | None) -> datetime | None:
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

    raise TypeError(f"normalize_to_utc_datetime requires date or datetime, got {type(dt).__name__}")


def safe_limit(limit_str: str | None, max_val: int = 5000, default: int | None = None) -> int:
    """Parse and validate limit parameter. Optionally use default if missing.

    Args:
        limit_str: Limit value (string or None)
        max_val: Maximum allowed value
        default: Default value if limit_str is None/empty. If None, raises error on missing.

    Returns:
        Validated limit value (between 1 and max_val)

    Raises:
        BadRequest: If limit_str invalid and no default provided
    """
    if not limit_str:
        if default is not None:
            return min(max(default, 1), max_val)
        raise_api_error(400, "BadRequest", "limit parameter is required")
        return max_val  # unreachable
    try:
        value = int(limit_str)
        if value <= 0:
            raise_api_error(400, "BadRequest", "limit must be greater than 0")
            return max_val  # unreachable
        return min(value, max_val)
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "limit must be a valid integer")
        return max_val  # unreachable


def safe_offset(offset_str: str | None, max_val: int = 1000000) -> int:
    """Parse and validate offset parameter. Always fails fast on invalid input."""
    if not offset_str:
        raise_api_error(400, "BadRequest", "offset parameter is required")
        return 0  # unreachable
    try:
        value = int(offset_str)
        if value < 0:
            raise_api_error(400, "BadRequest", "offset must be non-negative")
            return 0  # unreachable
        return min(value, max_val)
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "offset must be a valid integer")
        return 0  # unreachable


def safe_days(days_str: str | None, max_val: int = 365, default: int | None = None) -> int:
    """Parse and validate days parameter. Optionally use default if missing.

    Args:
        days_str: Days value (string or None)
        max_val: Maximum allowed value
        default: Default value if days_str is None/empty. If None, raises error on missing.

    Returns:
        Validated days value (between 1 and max_val)

    Raises:
        BadRequest: If days_str invalid and no default provided
    """
    if not days_str:
        if default is not None:
            return min(max(default, 1), max_val)
        raise_api_error(400, "BadRequest", "days parameter is required")
        return max_val  # unreachable
    try:
        value = int(days_str)
        if value < 1:
            raise_api_error(400, "BadRequest", "days must be at least 1")
            return max_val  # unreachable
        return min(value, max_val)
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "days must be a valid integer")
        return max_val  # unreachable


def safe_page(page_str: str | None, default: int | None = None) -> int:
    """Parse and validate page parameter. Optionally use default if missing.

    Args:
        page_str: Page value (string or None)
        default: Default value if page_str is None/empty. If None, raises error on missing.

    Returns:
        Validated page number (>= 1)

    Raises:
        BadRequest: If page_str invalid and no default provided
    """
    if not page_str:
        if default is not None:
            return max(default, 1)
        raise_api_error(400, "BadRequest", "page parameter is required")
        return 1  # unreachable
    try:
        value = int(page_str)
        if value < 1:
            raise_api_error(400, "BadRequest", "page must be at least 1")
            return 1  # unreachable
        return value
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "page must be a valid integer")
        return 1  # unreachable


def safe_int(int_str: str | None, min_val: int | None = None, max_val: int | None = None) -> int:
    """Parse and validate integer parameter. Always fails fast on invalid input."""
    if int_str is None or int_str == "":
        raise_api_error(400, "BadRequest", "parameter is required")
    try:
        value = int(int_str)
        if min_val is not None and value < min_val:
            raise_api_error(400, "BadRequest", f"value must be at least {min_val}")
        if max_val is not None and value > max_val:
            raise_api_error(400, "BadRequest", f"value must be at most {max_val}")
        return value
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "value must be a valid integer")


def safe_float(float_str: str | None, min_val: float | None = None, max_val: float | None = None) -> float:
    """Parse and validate float parameter. Always fails fast on invalid input."""
    if float_str is None or float_str == "":
        raise_api_error(400, "BadRequest", "parameter is required")
    try:
        value = float(float_str)
        if min_val is not None and value < min_val:
            raise_api_error(400, "BadRequest", f"value must be at least {min_val}")
        if max_val is not None and value > max_val:
            raise_api_error(400, "BadRequest", f"value must be at most {max_val}")
        return value
    except (ValueError, TypeError):
        raise_api_error(400, "BadRequest", "value must be a valid float")


def safe_string(value_str: str | None, allowed_values: set[str] | None = None, max_length: int = 100) -> str:
    """Validate and sanitize string parameter. Always fails fast on invalid input.

    Args:
        value_str: String to validate
        allowed_values: Set of allowed values (whitelist)
        max_length: Maximum allowed length

    Returns:
        Validated string

    Raises:
        BadRequest: If validation fails
    """
    if not value_str:
        raise_api_error(400, "BadRequest", "parameter is required")

    value_str = str(value_str)

    # Enforce max length
    if len(value_str) > max_length:
        raise_api_error(400, "BadRequest", f"value exceeds maximum length of {max_length}")

    # Check against whitelist if provided
    if allowed_values is not None:
        if value_str not in allowed_values:
            raise_api_error(400, "BadRequest", f"value must be one of: {', '.join(allowed_values)}")

    return value_str


def safe_symbol(symbol_str: str | None) -> str:
    """Validate stock symbol (alphanumeric + dash + caret for indices). Always fails fast.

    Args:
        symbol_str: Symbol to validate

    Returns:
        Validated symbol in uppercase

    Raises:
        BadRequest: If validation fails
    """
    if not symbol_str:
        raise_api_error(400, "BadRequest", "symbol parameter is required")

    symbol = str(symbol_str).upper()
    if len(symbol) > 10:
        raise_api_error(400, "BadRequest", "symbol must be 10 characters or less")

    if not all(c.isalnum() or c in "-^." for c in symbol):
        raise_api_error(400, "BadRequest", "symbol contains invalid characters")

    return symbol


def get_api_version_headers() -> dict[str, str]:
    """Return API version header for all responses.

    Includes X-API-Version header so clients and monitoring systems can detect
    schema changes and breaking API modifications.

    Returns:
        Dict with X-API-Version header
    """
    from api_utils.config import API_VERSION, API_VERSION_HEADER

    return {API_VERSION_HEADER: API_VERSION}


def error_response(code: int, typ: str, msg: str) -> dict[str, Any]:
    """Standardized error response.

    Returns consistent error format with statusCode, errorType, message, and _error.
    All error responses include HTTP status code for client-side error handling.
    The _error field enables consistent error detection across the dashboard.

    DEPRECATED: Prefer raising APIException subclasses instead.
    Use raise_api_error() or raise_db_error() helper functions.
    """
    # Sanitize message to remove credentials, paths, SQL
    from utils.error_handlers import sanitize_error_message

    msg = sanitize_error_message(msg)

    return {"statusCode": code, "errorType": typ, "message": msg, "_error": msg}


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


def extract_param(params, key: str, required: bool = False, default: str | None = None) -> str | None:
    """Extract parameter from CGI-style params dict (dict of lists).

    Args:
        params: Query parameters as dict of lists (from urllib.parse.parse_qs)
        key: Parameter name to extract
        required: If True, raise error if parameter missing
        default: Default value if parameter missing and not required

    Returns:
        Parameter value (first element from list) or default

    Raises:
        BadRequest: If required parameter is missing
    """
    if not params or key not in params or not params[key]:
        if required:
            raise_api_error(400, "BadRequest", f"Required parameter missing: {key}")
        return default

    value = params[key][0] if isinstance(params[key], list) else params[key]
    return (
        value
        if value
        else (default if not required else (raise_api_error(400, "BadRequest", f"Required parameter missing: {key}")))
    )


def raise_api_error(status_code: int, error_type: str, message: str) -> NoReturn:
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


def success_response(data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
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
) -> dict[str, Any]:
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

    if not isinstance(timeout_sec, (int, float)):
        raise TypeError(f"timeout_sec must be numeric, got {type(timeout_sec).__name__}")
    current_timeout: float = float(timeout_sec)
    last_error = None

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
            return cur.fetchall()

        except psycopg2.errors.QueryCanceled as e:
            last_error = e
            if attempt < max_attempts - 1:
                current_timeout *= backoff_multiplier
                with log_sanitizer("query timeout retry") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
                    logger.debug(f"Failed to rollback after query timeout: {rollback_err}")
                time.sleep(0.1)
            else:
                with log_sanitizer("query timeout final") as safe_log:
                    safe_log.warning(e)
                try:
                    cur.connection.rollback()
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
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


def check_data_freshness(cur, table_name: str, date_column: str = "date", warning_days: int | None = None) -> dict[str, Any]:
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
    except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError, ZeroDivisionError, TypeError) as e:
        # Fail fast on data freshness check errors — don't silently mark as stale
        # Caller should know if freshness verification failed, not assume stale
        logger.error(f"[DATA_FRESHNESS] Failed to check freshness for {table_name}: {e}")
        raise


def json_response(code: int, data: dict[str, Any], data_freshness: dict[str, Any] | None = None) -> dict[str, Any]:
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
        error_resp: dict[str, Any] = {"statusCode": code, **sanitized_data}
        if "_error" not in error_resp and has_non_none_message:
            error_resp["_error"] = sanitized_data["message"]
        return error_resp


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


def safe_dict_convert(row: Any) -> dict[str, Any]:
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
        raise ValueError("Database row is None — cannot convert None to dict")

    try:
        return dict(row)
    except (KeyError, ValueError, TypeError) as e:
        row_keys = list(row.keys()) if hasattr(row, "keys") else "unknown"
        raise RuntimeError(
            f"Failed to convert database row to dict: {type(e).__name__}: {e}\n"
            f"  Row keys: {row_keys}\n"
            f"  Row type: {type(row).__name__}\n"
            f"  This may indicate a schema mismatch between code and database."
        )


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
