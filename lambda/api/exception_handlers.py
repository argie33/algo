"""
Standardized exception handling for API handler.
Replaces bare except blocks with specific exception types and proper logging context.
"""

import logging
from utils.db_connection import get_db_connection
import psycopg2.errors
from typing import Dict, Any, Optional, Callable, Tuple
import traceback

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Base exception for API errors."""
    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class DatabaseException(APIException):
    """Database operation failed."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__('database_error', message, 503)
        self.original_error = original_error


class ValidationException(APIException):
    """Invalid input data."""
    def __init__(self, message: str):
        super().__init__('validation_error', message, 400)


class AuthenticationException(APIException):
    """Authentication failed."""
    def __init__(self, message: str = 'Authentication required'):
        super().__init__('auth_error', message, 401)


class NotFoundException(APIException):
    """Resource not found."""
    def __init__(self, resource: str):
        super().__init__('not_found', f'{resource} not found', 404)


def handle_database_error(error: Exception, operation: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Handle database errors with proper logging and safe error messages.

    Args:
        error: The exception that occurred
        operation: What operation was being attempted (e.g., 'fetch positions')
        context: Additional context (symbol, endpoint, etc.)

    Returns:
        Error response dict safe to return to client
    """
    context = context or {}

    # Log full error for debugging
    logger.error(
        f"Database error during {operation}",
        extra={
            'error_type': type(error).__name__,
            'operation': operation,
            'context': context,
            'traceback': traceback.format_exc()
        }
    )

    # Return safe message to client based on error type
    if isinstance(error, psycopg2.errors.UndefinedTable):
        return {
            'success': False,
            'error': {
                'code': 'schema_error',
                'message': 'Required data not yet loaded. Check data pipeline status.',
                'status': 503
            }
        }
    elif isinstance(error, psycopg2.errors.UndefinedColumn):
        return {
            'success': False,
            'error': {
                'code': 'schema_error',
                'message': 'Data schema mismatch. Contact administrator.',
                'status': 503
            }
        }
    elif isinstance(error, psycopg2.OperationalError):
        return {
            'success': False,
            'error': {
                'code': 'database_unavailable',
                'message': 'Database connection failed. Try again.',
                'status': 503
            }
        }
    elif isinstance(error, psycopg2.IntegrityError):
        return {
            'success': False,
            'error': {
                'code': 'data_conflict',
                'message': 'Data conflict. Ensure no duplicates.',
                'status': 409
            }
        }
    else:
        # Generic database error
        return {
            'success': False,
            'error': {
                'code': 'database_error',
                'message': 'Database operation failed.',
                'status': 500
            }
        }


def safe_execute(func: Callable, operation: str, context: Dict[str, Any] = None) -> Tuple[bool, Optional[str], Optional[Any]]:
    """
    Execute function with exception handling.

    Args:
        func: Function to execute
        operation: Description of operation
        context: Additional context

    Returns:
        (success, error_message, result)
    """
    context = context or {}

    try:
        result = func()
        return True, None, result
    except psycopg2.DatabaseError as e:
        msg = f"Database error during {operation}: {str(e)}"
        logger.error(msg, extra={'context': context, 'error_type': type(e).__name__})
        return False, msg, None
    except psycopg2.OperationalError as e:
        msg = f"Database connection failed during {operation}"
        logger.error(msg, extra={'context': context})
        return False, msg, None
    except ValueError as e:
        msg = f"Invalid value during {operation}: {str(e)}"
        logger.warning(msg, extra={'context': context})
        return False, msg, None
    except KeyError as e:
        msg = f"Missing key during {operation}: {str(e)}"
        logger.warning(msg, extra={'context': context})
        return False, msg, None
    except TypeError as e:
        msg = f"Type error during {operation}: {str(e)}"
        logger.error(msg, extra={'context': context})
        return False, msg, None
    except Exception as e:
        msg = f"Unexpected error during {operation}: {type(e).__name__}"
        logger.error(msg, extra={'context': context, 'error': str(e), 'traceback': traceback.format_exc()})
        return False, msg, None


def safe_db_query(cur, query: str, params: Tuple = (), operation: str = 'database query') -> Tuple[bool, Optional[str], Optional[Any]]:
    """
    Execute database query with error handling.

    Args:
        cur: Database cursor
        query: SQL query
        params: Query parameters
        operation: Description of operation

    Returns:
        (success, error_message, result)
    """
    try:
        cur.execute(query, params)
        return True, None, cur.fetchall()
    except psycopg2.errors.UndefinedTable as e:
        msg = f"Table not found during {operation}. Data may not be loaded yet."
        logger.error(msg, extra={'operation': operation, 'query': query})
        return False, msg, None
    except psycopg2.errors.UndefinedColumn as e:
        msg = f"Column not found during {operation}. Schema mismatch."
        logger.error(msg, extra={'operation': operation, 'query': query})
        return False, msg, None
    except psycopg2.DatabaseError as e:
        msg = f"Database error during {operation}"
        logger.error(msg, extra={'operation': operation, 'error': str(e)})
        return False, msg, None
    except psycopg2.OperationalError as e:
        msg = f"Connection error during {operation}"
        logger.error(msg, extra={'operation': operation})
        return False, msg, None
    except Exception as e:
        msg = f"Query failed during {operation}: {type(e).__name__}"
        logger.error(msg, extra={'operation': operation, 'error': str(e), 'traceback': traceback.format_exc()})
        return False, msg, None
