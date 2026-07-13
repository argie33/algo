"""Error handlers for Lambda API - delegates to shared utils.error_handlers.

Consolidates duplicate implementations into single source of truth to prevent
divergence (especially critical for sanitize_error_message PII handling).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.errors

from utils.error_handlers import sanitize_error_message

logger = logging.getLogger(__name__)


@contextmanager
def log_sanitizer(operation: str = "operation") -> Any:
    """Context manager for safe error logging with automatic sanitization."""

    class SanitizedLogger:
        def __init__(self, op: str) -> None:
            self.op = op

        def error(self, message: Any, context: dict[str, Any] | None = None) -> None:
            msg = f"{self.op}: {message}"
            if context:
                msg += f" (context: {context})"
            logger.error(msg)

        def warning(self, message: Any, context: dict[str, Any] | None = None) -> None:
            msg = f"{self.op}: {message}"
            if context:
                msg += f" (context: {context})"
            logger.warning(msg)

    yield SanitizedLogger(operation)


def classify_exception(error: Exception) -> tuple[int, str, str]:
    """Classify an exception and return HTTP status code, error type, and message."""
    if isinstance(error, psycopg2.errors.UndefinedTable):
        return 404, "not_found", "Database table not found"
    if isinstance(error, psycopg2.errors.UndefinedColumn):
        return 404, "not_found", "Database column not found"
    if isinstance(error, psycopg2.OperationalError):
        return 503, "service_unavailable", "Database connection error"
    if isinstance(error, psycopg2.DatabaseError):
        return 500, "database_error", "Database error"
    if isinstance(error, psycopg2.IntegrityError):
        return 409, "conflict", "Data integrity error"
    if isinstance(error, psycopg2.ProgrammingError):
        return 400, "bad_request", "Invalid SQL"
    return 500, "internal_error", "Unexpected error"


def extract_error_context(e: Exception) -> dict[str, Any]:
    """Extract context from an exception."""
    return {
        "error_type": type(e).__name__,
        "error_message": str(e),
        "error_module": type(e).__module__,
    }


def log_error_with_context(e: Exception, context: dict[str, Any] | None = None) -> None:
    """Log an error with context."""
    msg = f"Error: {type(e).__name__}: {e!s}"
    if context:
        msg += f" | {context}"
    logger.error(msg)


def make_error_response(status_code: int, error_type: str, message: str) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "error": {
            "type": error_type,
            "message": sanitize_error_message(message),
        },
    }


def retry_with_backoff(func: Any, max_attempts: int = 3, backoff_base: float = 1.0) -> Any:
    """Retry a function with exponential backoff."""
    import time

    for attempt in range(max_attempts):
        try:
            return func()
        except Exception:
            if attempt == max_attempts - 1:
                raise
            wait_time = backoff_base**attempt
            time.sleep(wait_time)


__all__ = [
    "classify_exception",
    "extract_error_context",
    "log_error_with_context",
    "log_sanitizer",
    "make_error_response",
    "retry_with_backoff",
    "sanitize_error_message",
]
