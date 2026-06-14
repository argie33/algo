"""Unified error classification and handling utilities.

Maps any exception type to standardized (statusCode, errorType, message).
Provides helpers for error logging, sanitization, and context extraction.
"""

import logging
import re
from typing import Tuple, Dict, Any, Optional
from datetime import datetime

try:
    import psycopg2
    import psycopg2.errors
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from utils.exceptions import (
    BaseAPIException,
    DatabaseConnectionError,
    DatabaseQueryTimeout,
    DatabaseSchemaError,
    DatabaseConstraintViolation,
    InputValidationError,
    DataQualityError,
    ExternalAPITimeout,
    ExternalAPIError,
    RateLimitedError,
    ServiceUnavailableError,
    UnexpectedError,
)

logger = logging.getLogger(__name__)


def classify_exception(e: Exception) -> Tuple[int, str, str]:
    """Map any exception to (statusCode, errorType, message).

    Converts standard exceptions and custom BaseAPIException to standardized format.

    Args:
        e: Exception instance

    Returns:
        Tuple of (statusCode, errorType, message)
    """
    if isinstance(e, BaseAPIException):
        return (e.status_code, e.error_type, e.message)

    error_type_name = type(e).__name__
    error_str = str(e)

    # Database errors
    if HAS_PSYCOPG2:
        if isinstance(e, psycopg2.errors.UndefinedTable):
            return (503, 'schema_error', 'Database schema issue')
        elif isinstance(e, psycopg2.errors.UndefinedColumn):
            return (503, 'schema_error', 'Database schema issue')
        elif isinstance(e, psycopg2.errors.UniqueViolation):
            return (409, 'constraint_violation', 'Data constraint violated')
        elif isinstance(e, psycopg2.errors.ForeignKeyViolation):
            return (409, 'constraint_violation', 'Data constraint violated')
        elif isinstance(e, psycopg2.errors.QueryCanceled):
            return (504, 'timeout', 'Database query exceeded timeout')
        elif isinstance(e, psycopg2.OperationalError):
            return (503, 'connection_error', 'Database connection failed')
        elif isinstance(e, psycopg2.DatabaseError):
            return (503, 'query_error', 'Database query failed')

    # Timeout errors
    if 'timeout' in error_type_name.lower():
        return (504, 'timeout', 'Operation timed out')

    # Connection/network errors
    if 'connection' in error_type_name.lower() or 'connection' in error_str.lower():
        return (502, 'connection_error', 'Connection failed')

    # Validation errors
    if 'validation' in error_type_name.lower():
        return (400, 'validation_error', 'Invalid input provided')
    if 'valueerror' in error_type_name.lower():
        return (400, 'bad_request', 'Invalid input provided')

    # Value/Type errors
    if error_type_name in ('ValueError', 'TypeError', 'KeyError', 'AttributeError'):
        return (400, 'bad_request', 'Invalid request')

    # File/resource errors
    if error_type_name in ('FileNotFoundError', 'IOError', 'OSError'):
        return (500, 'resource_error', 'Resource access failed')

    # Default to 500 internal error
    return (500, 'internal_error', 'An error occurred')


def log_error_with_context(
    e: Exception,
    operation: str,
    context_dict: Optional[Dict[str, Any]] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> None:
    """Log error with full context for debugging.

    Args:
        e: Exception instance
        operation: Operation name for context
        context_dict: Additional context (query, params, table_name, etc)
        logger_instance: Logger to use (defaults to module logger)
    """
    if logger_instance is None:
        logger_instance = logger

    status_code, error_type, message = classify_exception(e)
    log_msg = f'[{error_type.upper()}] {operation}: {message}\n'
    log_msg += f'  Exception: {type(e).__name__}: {str(e)[:500]}\n'

    if context_dict:
        for key, value in context_dict.items():
            value_str = str(value)[:200]
            log_msg += f'  {key}: {value_str}\n'

    if status_code >= 500:
        logger_instance.error(log_msg, exc_info=True)
    else:
        logger_instance.warning(log_msg)


def sanitize_error_message(msg: str) -> str:
    """Remove sensitive info (credentials, SQL, internal details) from message.

    Prevents credential leaks and SQL injection details from being exposed.

    Args:
        msg: Raw error message

    Returns:
        Sanitized message safe to return to client
    """
    # Remove connection strings
    msg = re.sub(r'password=\S+', 'password=***', msg, flags=re.IGNORECASE)
    msg = re.sub(r'api[_-]?key=\S+', 'api_key=***', msg, flags=re.IGNORECASE)
    msg = re.sub(r'token=\S+', 'token=***', msg, flags=re.IGNORECASE)

    # Remove file paths
    msg = re.sub(r'(/[a-zA-Z0-9_/.-]+)+', '/path/..', msg)
    msg = re.sub(r'([A-Z]:\\[a-zA-Z0-9_\\.\-]+)+', 'C:\\\\path\\\\...', msg)

    # Remove SQL if too long (indicates stack trace)
    if 'SELECT' in msg or 'INSERT' in msg or 'UPDATE' in msg:
        msg = 'Database operation failed'

    return msg


def extract_error_context(e: Exception) -> Dict[str, Any]:
    """Extract query, params, table_name, etc from exception for logging.

    Args:
        e: Exception instance

    Returns:
        Dict with extracted context (may be empty if not applicable)
    """
    context = {}

    # Extract from psycopg2 exceptions
    if HAS_PSYCOPG2 and isinstance(e, psycopg2.extensions.Diagnostic):
        context['context'] = str(e.context)
        context['statement'] = str(e.statement)

    # Extract from exception string (heuristic)
    e_str = str(e)
    if 'query' in e_str.lower():
        context['query_mentioned'] = True
    if 'table' in e_str.lower():
        context['table_mentioned'] = True

    # Add exception type
    context['exception_type'] = type(e).__name__

    return context


def retry_with_backoff(
    func,
    max_attempts: int = 3,
    initial_backoff_sec: float = 1.0,
    max_backoff_sec: float = 30.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
) -> Any:
    """Generic retry with exponential backoff.

    Args:
        func: Callable that returns result or raises exception
        max_attempts: Number of retry attempts
        initial_backoff_sec: Initial backoff in seconds
        max_backoff_sec: Maximum backoff cap
        backoff_multiplier: Multiply backoff by this each retry
        jitter: Add random jitter to backoff

    Returns:
        Result of func on success

    Raises:
        Exception: Last exception if all retries fail
    """
    import time
    import random

    last_error = None
    current_backoff = initial_backoff_sec

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_attempts - 1:
                if jitter:
                    actual_backoff = current_backoff * (0.5 + random.random())
                else:
                    actual_backoff = current_backoff

                actual_backoff = min(actual_backoff, max_backoff_sec)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed, retrying in {actual_backoff:.1f}s: {e}"
                )
                time.sleep(actual_backoff)
                current_backoff *= backoff_multiplier
            else:
                logger.error(f"All {max_attempts} attempts failed")

    if last_error:
        raise last_error


def make_error_response(
    e: Exception,
    operation: str = 'unknown operation',
    context_dict: Optional[Dict[str, Any]] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Create standardized error response from any exception.

    Logs the error with full context, classifies it, and returns API response.

    Args:
        e: Exception instance
        operation: Operation name for logging
        context_dict: Additional context for logging
        logger_instance: Logger to use

    Returns:
        Dict ready to return as API response
    """
    # Log with full context
    log_error_with_context(e, operation, context_dict, logger_instance)

    # Classify and create response
    status_code, error_type, message = classify_exception(e)

    # Sanitize message (remove credentials, paths, SQL)
    safe_message = sanitize_error_message(message)

    return {
        'statusCode': status_code,
        'errorType': error_type,
        'message': safe_message,
        '_error': error_type,
    }
