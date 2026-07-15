"""Unified error classification and handling utilities.

Maps any exception type to standardized (statusCode, errorType, message).
Provides helpers for error logging, sanitization, and context extraction.
"""

import logging
import re
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.errors

from utils.exceptions import (
    BaseAPIError,
)

logger = logging.getLogger(__name__)

# Check if psycopg2 is available
try:
    import psycopg2.extensions

    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


@contextmanager
def log_sanitizer(operation: str = "operation") -> Any:
    """Context manager for safe error logging with automatic sanitization.

    Prevents accidental PII leakage to CloudWatch by intercepting log calls
    and redacting sensitive fields (credentials, SQL, user data).

    Usage:
        with log_sanitizer("fetch user data") as safe_log:
            try:
                # risky operation
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                safe_log.error(e, context={"user_id": user_id})

    Args:
        operation: Operation name for context in error messages

    Yields:
        Sanitized logger wrapper with error() and warning() methods
    """

    class SanitizedLogger:
        def __init__(self, logger_inst: logging.Logger, op: str) -> None:
            self.logger = logger_inst
            self.operation = op

        def error(self, exc: Exception, context: dict[str, Any] | None = None) -> None:
            """Log error with automatic sanitization."""
            self._log_sanitized(exc, context, level="error")

        def warning(self, exc: Exception, context: dict[str, Any] | None = None) -> None:
            """Log warning with automatic sanitization."""
            self._log_sanitized(exc, context, level="warning")

        def _log_sanitized(
            self,
            exc: Exception,
            context: dict[str, Any] | None = None,
            level: str = "error",
        ) -> None:
            """Internal method to log with full sanitization."""
            _status_code, error_type, message = classify_exception(exc)

            # Sanitize exception message
            exc_str = sanitize_error_message(str(exc)[:500])

            log_msg = f"[{error_type.upper()}] {self.operation}: {message}\n"
            log_msg += f"  Exception: {type(exc).__name__}: {exc_str}\n"

            # Sanitize context dict
            if context:
                for key, value in context.items():
                    # Skip logging param values if they look like data
                    if key in ("params", "query", "sql"):
                        value_str = "[REDACTED SQL]"
                    elif key in ("password", "api_key", "token", "secret"):
                        value_str = "[REDACTED CREDENTIAL]"
                    elif isinstance(value, (list, dict)):
                        value_str = "[REDACTED DATA STRUCTURE]"
                    else:
                        value_str = sanitize_error_message(str(value)[:200])

                    log_msg += f"  {key}: {value_str}\n"

            # Log using the appropriate level
            if level == "error":
                self.logger.error(log_msg)
            else:
                self.logger.warning(log_msg)

    yield SanitizedLogger(logger, operation)


def classify_exception(e: Exception) -> tuple[int, str, str]:
    """Map any exception to (statusCode, errorType, message).

    Converts standard exceptions and custom BaseAPIError to standardized format.

    Args:
        e: Exception instance

    Returns:
        Tuple of (statusCode, errorType, message)
    """
    if isinstance(e, BaseAPIError):
        return (e.status_code, e.error_type, e.message)

    error_type_name = type(e).__name__
    error_str = str(e)

    # Database errors
    if isinstance(e, psycopg2.errors.UndefinedTable):
        return (503, "schema_error", "Database schema issue")
    elif isinstance(e, psycopg2.errors.UndefinedColumn):
        return (503, "schema_error", "Database schema issue")
    elif isinstance(e, psycopg2.errors.UniqueViolation):
        return (409, "constraint_violation", "Data constraint violated")
    elif isinstance(e, psycopg2.errors.ForeignKeyViolation):
        return (409, "constraint_violation", "Data constraint violated")
    elif isinstance(e, psycopg2.errors.QueryCanceled):
        return (504, "timeout", "Database query exceeded timeout")
    elif isinstance(e, psycopg2.OperationalError):
        return (503, "connection_error", "Database connection failed")
    elif isinstance(e, psycopg2.DatabaseError):
        return (503, "query_error", "Database query failed")

    # Timeout errors
    if "timeout" in error_type_name.lower():
        return (504, "timeout", "Operation timed out")

    # Connection/network errors
    if "connection" in error_type_name.lower() or "connection" in error_str.lower():
        return (502, "connection_error", "Connection failed")

    # Validation errors
    if "validation" in error_type_name.lower():
        return (400, "validation_error", "Invalid input provided")
    if "valueerror" in error_type_name.lower():
        return (400, "bad_request", "Invalid input provided")

    # Value/Type errors
    if error_type_name in ("ValueError", "TypeError", "KeyError", "AttributeError"):
        return (400, "bad_request", "Invalid request")

    # File/resource errors
    if error_type_name in ("FileNotFoundError", "IOError", "OSError"):
        return (500, "resource_error", "Resource access failed")

    # Default to 500 internal error
    return (500, "internal_error", "An error occurred")


def log_error_with_context(
    e: Exception,
    operation: str,
    context_dict: dict[str, Any] | None = None,
    logger_instance: logging.Logger | None = None,
) -> None:
    """Log error with full context for debugging.

    Uses sanitization to prevent PII/SQL leakage to CloudWatch logs.

    Args:
        e: Exception instance
        operation: Operation name for context
        context_dict: Additional context (query, params, table_name, etc)
        logger_instance: Logger to use (defaults to module logger)
    """
    if logger_instance is None:
        logger_instance = logger

    with log_sanitizer(operation) as safe_log:
        status_code, _, _ = classify_exception(e)
        if status_code >= 500:
            safe_log.error(e, context=context_dict)
        else:
            safe_log.warning(e, context=context_dict)


def sanitize_error_message(msg: str) -> str:
    """Remove sensitive info (credentials, SQL, IPs, paths) from message.

    Prevents credential leaks, SQL injection details, IPs, and file paths from
    being exposed to clients or logs. Does NOT redact email addresses - those
    are frequently legitimate, non-sensitive content in user-facing messages
    (e.g. validation errors echoing back a submitted value).

    Args:
        msg: Raw error message

    Returns:
        Sanitized message safe to return to client or log
    """
    if not isinstance(msg, str):
        return str(msg)

    # Remove SQL query details (anything between common SQL keywords).
    # CRITICAL: keywords must be word-bounded - without \b, bare "ON" (IGNORECASE)
    # matches the substring "on" inside ordinary words like "conn[on]ection",
    # corrupting any message containing "connection", "on", "front", etc.
    sanitized = re.sub(
        r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|ON)\b.*?(;|$)",
        "[SQL]",
        msg,
        flags=re.IGNORECASE,
    )

    # Remove file paths (Unix and Windows)
    sanitized = re.sub(r"(/[a-zA-Z0-9/_.-]*)+", "[path]", sanitized)
    sanitized = re.sub(r"([A-Z]:\\[a-zA-Z0-9_\\.\-]+)+", "[path]", sanitized)

    # Remove credential values (password, token, key, api_key, secret) - keeps the
    # keyword itself (e.g. "password=[redacted]") so the message stays useful for
    # debugging without leaking the actual secret value.
    sanitized = re.sub(
        r"(password|token|secret|key|api[_-]?key)[\s=:]*[^,\s]+",
        r"\1=[redacted]",
        sanitized,
        flags=re.IGNORECASE,
    )

    # Remove IP addresses
    sanitized = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[ip]", sanitized)

    return sanitized


def extract_error_context(e: Exception) -> dict[str, Any]:
    """Extract query, params, table_name, etc from exception for logging.

    Args:
        e: Exception instance

    Returns:
        Dict with extracted context (may be empty if not applicable)
    """
    context: dict[str, Any] = {}

    # Extract from psycopg2 exceptions
    if HAS_PSYCOPG2 and isinstance(e, psycopg2.extensions.Diagnostic):
        context["context"] = str(e.context)
        context["statement"] = str(e.statement)

    # Extract from exception string (heuristic)
    e_str = str(e)
    if "query" in e_str.lower():
        context["query_mentioned"] = True
    if "table" in e_str.lower():
        context["table_mentioned"] = True

    # Add exception type
    context["exception_type"] = type(e).__name__

    return context


def retry_with_backoff(
    func: Any,
    max_attempts: int = 3,
    initial_backoff_sec: float = 1.0,
    max_backoff_sec: float = 30.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
) -> Any:
    """Generic retry with exponential backoff.

    Logs retries with automatic PII/SQL sanitization.

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
    import random
    import time

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
                with log_sanitizer(f"retry attempt {attempt + 1}/{max_attempts}") as safe_log:
                    safe_log.warning(e)
                time.sleep(actual_backoff)
                current_backoff *= backoff_multiplier
            else:
                with log_sanitizer("retry exhausted") as safe_log:
                    safe_log.error(e)

    if last_error:
        raise last_error


def make_error_response(
    e: Exception,
    operation: str = "unknown operation",
    context_dict: dict[str, Any] | None = None,
    logger_instance: logging.Logger | None = None,
) -> dict[str, Any]:
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

    response = {
        "statusCode": status_code,
        "errorType": error_type,
        "message": safe_message,
        "_error": safe_message,
    }
    # Mark 503 errors as transient so dashboard fetchers retry with exponential backoff
    if status_code == 503:
        response["_is_transient_503"] = True
    return response
