"""Shared route utilities."""
import psycopg2.errors
import logging
import time

logger = logging.getLogger(__name__)

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

    if not all(c.isalnum() or c in '-^.' for c in symbol):
        return None

    return symbol

def error_response(code, typ, msg):
    """Standardized error response.

    Returns consistent error format with statusCode, errorType, and message.
    All error responses include HTTP status code for client-side error handling.
    """
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data, metadata=None):
    """Standardized success response for single object.

    Always returns object with statusCode=200 and data field.
    Optionally includes additional metadata (freshness, etc).
    """
    response = {"statusCode": 200, "data": data}
    if metadata:
        response.update(metadata)
    return response

def list_response(items, total=None, data_freshness=None, limit=None, offset=None):
    """Standardized list response for paginated data.

    Always returns array in 'items' field with total count.
    Includes pagination metadata for client-side pagination.
    Format: {statusCode: 200, items: [...], total: X, limit?: Y, offset?: Z}
    """
    response = {
        "statusCode": 200,
        "items": items if items else [],
        "total": total if total is not None else len(items if items else [])
    }
    if limit is not None:
        response["limit"] = limit
    if offset is not None:
        response["offset"] = offset
    if data_freshness:
        response["data_freshness"] = data_freshness
    return response

def execute_with_timeout(cur, query: str, params=None, timeout_sec: int = 10, max_attempts: int = 2, backoff_multiplier: float = 1.5):
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
        Query result (list of rows) on success, empty list on failure

    Raises:
        None — logs errors and returns empty result on failure
    """
    current_timeout = timeout_sec
    last_error = None

    for attempt in range(max_attempts):
        try:
            # Set LOCAL timeout (connection-scoped, not global)
            cur.execute(f"SET LOCAL statement_timeout = '{int(current_timeout * 1000)}ms'")
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            return cur.fetchall()

        except psycopg2.errors.QueryCanceled as e:
            last_error = e
            if attempt < max_attempts - 1:
                current_timeout *= backoff_multiplier
                logger.warning(
                    f"Query timeout (attempt {attempt + 1}/{max_attempts}, timeout={int(current_timeout * 1000)}ms) — retrying with increased timeout"
                )
                try:
                    cur.connection.rollback()
                except Exception:
                    pass
                time.sleep(0.1)
            else:
                logger.warning(f"Query timeout after {max_attempts} attempts")
        except Exception as e:
            last_error = e
            logger.error(f"Query failed ({type(e).__name__}): {str(e)}")
            try:
                cur.connection.rollback()
            except Exception:
                pass
            break

    # Log final error if all attempts failed
    if last_error:
        logger.error(f"Query execution failed after {max_attempts} attempts: {last_error}")

    return []

def check_data_freshness(cur, table_name: str, date_column: str = "date", warning_days: int = 1) -> dict:
    """Check how fresh data is in a table.

    Args:
        cur: Database cursor
        table_name: Table to check
        date_column: Column containing date/timestamp
        warning_days: Days beyond which data is considered stale

    Returns:
        Dict with data_age_days, is_stale, max_date, warning
    """
    try:
        import psycopg2.sql
        cur.execute(
            psycopg2.sql.SQL("SELECT MAX({}) FROM {}").format(
                psycopg2.sql.Identifier(date_column),
                psycopg2.sql.Identifier(table_name)
            )
        )
        result = cur.fetchone()

        if not result or not result[0]:
            return {
                "data_age_days": None,
                "is_stale": True,
                "warning": f"No data in {table_name}"
            }

        from datetime import datetime, date
        max_date = result[0]

        # Handle both date and datetime objects
        if hasattr(max_date, 'date'):
            max_date = max_date.date()

        today = date.today()
        data_age = (today - max_date).days

        # Financial market data only updates on trading days (Mon–Fri).
        # Adjust the staleness threshold on weekends so Friday's data stays
        # "fresh" through Sunday without triggering false stale warnings.
        weekday = today.weekday()  # 0=Mon … 6=Sun
        if weekday == 5:    # Saturday: Friday data is 1 day old → +1
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
            "warning": f"Data is {data_age} days old" if is_stale else None
        }
    except Exception as e:
        # SECURITY FIX S-11: Don't expose database error details to client
        return {
            "data_age_days": None,
            "is_stale": True,
            "warning": "Unable to determine data freshness"
        }

def json_response(code, data):
    """Standardized JSON response wrapper for single objects.

    Returns consistent format:
    - Success (200): {statusCode: 200, data: {...}}
    - Error (4xx/5xx): {statusCode: code, errorType: "...", message: "..."}

    Always use success_response(data) or error_response(code, type, msg) instead of calling this directly.
    """
    if code == 200:
        return success_response(data)
    else:
        # For non-200 codes, data should have 'errorType' and 'message'
        return {"statusCode": code, **data}

def handle_db_error(e, context="database operation"):
    """Handle database errors with standardized response.

    Converts exception to appropriate HTTP error response.
    Returns: (statusCode, errorType, message)
    """
    error_type = type(e).__name__
    error_msg = str(e)

    # Timeout errors
    if 'QueryCanceled' in error_type or 'timeout' in error_msg.lower():
        return 504, 'timeout', 'Database query exceeded timeout'
    # Connection errors
    elif 'OperationalError' in error_type or 'Connection' in error_type:
        return 503, 'connection_error', 'Database connection failed'
    # Constraint/integrity errors
    elif 'IntegrityError' in error_type:
        return 400, 'integrity_error', 'Data constraint violation'
    # Schema errors
    elif 'UndefinedTable' in error_type or 'UndefinedColumn' in error_type:
        return 503, 'schema_error', 'Database schema mismatch'
    # Query syntax errors
    elif 'ProgrammingError' in error_type:
        return 400, 'query_error', 'Invalid query executed'
    # Generic database errors
    else:
        return 500, 'database_error', f'Error during {context}'

def handle_db_error(error, logger, operation):
    """Unified database error handler for all route handlers.

    Args:
        error: The exception caught
        logger: Logger instance
        operation: Operation name for logging context

    Returns:
        Appropriate error_response tuple based on error type
        Note: Returns specific error types to client for diagnostics (never exposes DB details)
    """
    import psycopg2

    # Log full details server-side for debugging
    error_type = type(error).__name__
    error_str = str(error)

    if isinstance(error, psycopg2.errors.UndefinedTable):
        logger.error(f'[DB_SCHEMA_ERROR] Table not found in {operation}: {error_str}')
        # Return specific error code for schema issues — clients can distinguish from connection errors
        return error_response(503, 'schema_error', 'Database schema issue')
    elif isinstance(error, psycopg2.errors.UndefinedColumn):
        logger.error(f'[DB_SCHEMA_ERROR] Column not found in {operation}: {error_str}')
        return error_response(503, 'schema_error', 'Database schema issue')
    elif isinstance(error, psycopg2.OperationalError):
        logger.error(f'[DB_CONNECTION_ERROR] Connection failed in {operation}: {error_str}')
        # Return specific error code for connection issues
        return error_response(503, 'connection_error', 'Database connection failed')
    elif isinstance(error, psycopg2.DatabaseError):
        logger.error(f'[DB_ERROR] Query failed in {operation}: {error_str}')
        # Return specific error code for query execution issues
        return error_response(503, 'query_error', 'Database query failed')
    else:
        logger.error(f'[UNEXPECTED_ERROR] {error_type} in {operation}: {error_str}')
        return error_response(500, 'internal_error', 'Internal server error')
