"""Centralized database error handling for consistent error messaging and logging."""

import contextlib
import logging
from typing import Generator

import psycopg2

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def handle_db_errors(context: str) -> Generator[None, None, None]:
    """Centralized database error handler for consistent error patterns.

    Catches psycopg2 errors and converts to RuntimeError with standardized messaging.

    Args:
        context: Context string for error message (e.g., "fetch_trading_dates")

    Raises:
        RuntimeError: On any database error with consistent format

    Example:
        with handle_db_errors("fetch_prices"):
            result = cursor.execute("SELECT ...")
    """
    try:
        yield
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        msg = f"[{context}] Database error: {e}"
        logger.error(msg)
        raise RuntimeError(msg) from e
