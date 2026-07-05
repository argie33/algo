"""Error handlers for database and API errors."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


def classify_exception(error: Exception) -> tuple[int, str, str]:
    """Classify an exception and return HTTP status code, error type, and message.

    Args:
        error: The exception to classify

    Returns:
        Tuple of (status_code: int, error_type: str, message: str)
    """
    # Database errors
    if isinstance(error, psycopg2.errors.UndefinedTable):
        return 404, "not_found", f"Database table not found: {error!s}"
    if isinstance(error, psycopg2.errors.UndefinedColumn):
        return 404, "not_found", f"Database column not found: {error!s}"
    if isinstance(error, psycopg2.OperationalError):
        return 503, "service_unavailable", f"Database connection error: {error!s}"
    if isinstance(error, psycopg2.DatabaseError):
        return 500, "database_error", f"Database error: {error!s}"
    if isinstance(error, psycopg2.IntegrityError):
        return 409, "conflict", f"Data integrity error: {error!s}"
    if isinstance(error, psycopg2.ProgrammingError):
        return 400, "bad_request", f"Invalid SQL: {error!s}"

    # Generic error fallback
    return 500, "internal_error", f"Unexpected error: {error!s}"


@contextmanager
def log_sanitizer(prefix: str):  # type: ignore[no-untyped-def]
    """Context manager for sanitized logging (prevents PII/SQL leakage).

    Args:
        prefix: Prefix for log messages

    Yields:
        A logger instance that sanitizes output
    """
    class SanitizedLogger:
        def __init__(self, prefix: str) -> None:
            self.prefix = prefix

        def error(self, message: Any, context: dict[str, Any] | None = None) -> None:
            """Log an error message safely."""
            msg = f"{self.prefix}: {message}"
            if context:
                msg += f" (context: {context})"
            logger.error(msg)

        def warning(self, message: Any, context: dict[str, Any] | None = None) -> None:
            """Log a warning message safely."""
            msg = f"{self.prefix}: {message}"
            if context:
                msg += f" (context: {context})"
            logger.warning(msg)

    yield SanitizedLogger(prefix)


def sanitize_error_message(message: str) -> str:
    """Sanitize error messages to remove sensitive information (PII, SQL, etc).

    Args:
        message: Error message to sanitize

    Returns:
        Sanitized error message safe for API response
    """
    if not isinstance(message, str):
        return str(message)

    # Remove SQL query details (anything between common SQL keywords)
    sanitized = re.sub(r'(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|ON).*?(;|$)', '[SQL]', message, flags=re.IGNORECASE)

    # Remove file paths and credentials
    sanitized = re.sub(r'(/[a-zA-Z0-9/_.-]*)', '[path]', sanitized)
    sanitized = re.sub(r'(password|token|secret|key)[\s=:]*[^,\s]+', r'\1=[redacted]', sanitized, flags=re.IGNORECASE)

    # Remove email addresses
    sanitized = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[email]', sanitized)

    # Remove IP addresses
    sanitized = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[ip]', sanitized)

    return sanitized
