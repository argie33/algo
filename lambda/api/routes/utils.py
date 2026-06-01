"""Shared route utilities."""

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
    """Validate stock symbol (alphanumeric + dash only)."""
    if not symbol_str:
        return None

    # Allow up to 5 chars, alphanumeric + dash (e.g., BRK-A)
    symbol = str(symbol_str).upper()
    if len(symbol) > 5:
        return None

    if not all(c.isalnum() or c == '-' for c in symbol):
        return None

    return symbol

def error_response(code, typ, msg):
    """Standardized error response."""
    return {"statusCode": code, "errorType": typ, "message": msg}

def success_response(data):
    """Standardized success response."""
    return {"statusCode": 200, "data": data}

def list_response(items, total=None, data_freshness=None):
    """Standardized list response with optional freshness metadata."""
    response = {"statusCode": 200, "items": items, "total": total or len(items)}
    if data_freshness:
        response["data_freshness"] = data_freshness
    return response

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

        data_age = (date.today() - max_date).days
        is_stale = data_age > warning_days

        return {
            "data_age_days": data_age,
            "is_stale": is_stale,
            "max_date": str(max_date),
            "warning": f"Data is {data_age} days old" if is_stale else None
        }
    except Exception as e:
        return {
            "data_age_days": None,
            "is_stale": True,
            "error": str(e)
        }

def json_response(code, data):
    """Standardized JSON response."""
    return {"statusCode": code, **data}

def handle_db_error(error, logger, operation):
    """Unified database error handler for all route handlers.

    Args:
        error: The exception caught
        logger: Logger instance
        operation: Operation name for logging context

    Returns:
        Appropriate error_response tuple based on error type
        Note: Always returns generic error message to client (never exposes DB details)
    """
    import psycopg2

    # SECURITY FIX: Log full details server-side but never expose to client
    error_type = type(error).__name__
    error_str = str(error)

    if isinstance(error, psycopg2.errors.UndefinedTable):
        logger.error(f'[DB_SCHEMA_ERROR] Table not found in {operation}: {error_str}')
        # Generic message to client - don't expose table names
        return error_response(503, 'service_unavailable', 'Service temporarily unavailable')
    elif isinstance(error, psycopg2.errors.UndefinedColumn):
        logger.error(f'[DB_SCHEMA_ERROR] Column not found in {operation}: {error_str}')
        return error_response(503, 'service_unavailable', 'Service temporarily unavailable')
    elif isinstance(error, psycopg2.OperationalError):
        logger.error(f'[DB_CONNECTION_ERROR] Connection failed in {operation}: {error_str}')
        return error_response(503, 'service_unavailable', 'Service temporarily unavailable')
    elif isinstance(error, psycopg2.DatabaseError):
        logger.error(f'[DB_ERROR] Query failed in {operation}: {error_str}')
        return error_response(503, 'service_unavailable', 'Service temporarily unavailable')
    else:
        logger.error(f'[UNEXPECTED_ERROR] {error_type} in {operation}: {error_str}')
        return error_response(500, 'internal_error', 'Service temporarily unavailable')
