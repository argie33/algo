"""Shared route utilities."""


def safe_limit(limit_str, max_val=50000, default=500):
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


def error_response(code, typ, msg):
    """Standardized error response."""
    return {"statusCode": code, "errorType": typ, "message": msg}


def success_response(data):
    """Standardized success response."""
    return {"statusCode": 200, "data": data}


def list_response(items, total=None):
    """Standardized list response."""
    return {"statusCode": 200, "items": items, "total": total or len(items)}


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
    """
    import psycopg2

    if isinstance(error, psycopg2.errors.UndefinedTable):
        logger.error(f'Required table not found: {error}', extra={'operation': operation})
        return error_response(503, 'service_unavailable', 'Data pipeline loading')
    elif isinstance(error, psycopg2.errors.UndefinedColumn):
        logger.error(f'Column not found: {error}', extra={'operation': operation})
        return error_response(503, 'service_unavailable', 'Data schema mismatch')
    elif isinstance(error, psycopg2.OperationalError):
        logger.error(f'Database connection error: {error}', extra={'operation': operation})
        return error_response(503, 'service_unavailable', 'Database unavailable')
    elif isinstance(error, psycopg2.DatabaseError):
        logger.error(f'Database error: {error}', extra={'operation': operation, 'error_type': type(error).__name__})
        return error_response(500, 'internal_error', 'Database query failed')
    else:
        logger.error(f'Unexpected error: {error}', extra={'operation': operation, 'error_type': type(error).__name__})
        return error_response(500, 'internal_error', 'Internal server error')
