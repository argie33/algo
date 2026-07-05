"""Context manager for PostgreSQL SAVEPOINT handling with automatic rollback on error."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


@contextmanager
def savepoint_context(
    cur: Any, savepoint_name: str, fallback_value: Any = None, log_errors: bool = True
) -> Generator[None, None, None]:
    """Context manager for SAVEPOINT blocks with automatic rollback on error.

    Usage:
        with savepoint_context(cur, "my_savepoint") as ctx:
            cur.execute(query1)
            result = cur.execute(query2)
            # If any exception occurs, savepoint is rolled back automatically

    Args:
        cur: Database cursor
        savepoint_name: Name of the savepoint
        fallback_value: Value to return if an error occurs (allows graceful degradation)
        log_errors: Whether to log errors (default True)

    Yields:
        None; use the cursor directly within the with block
    """
    try:
        cur.execute(f"SAVEPOINT {savepoint_name}")
        yield
        cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except (
        psycopg2.errors.QueryCanceled,  # pylint: disable=no-member
        psycopg2.errors.UndefinedTable,  # pylint: disable=no-member
        psycopg2.errors.UndefinedColumn,  # pylint: disable=no-member
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        if log_errors:
            logger.warning("[SAVEPOINT] Rolling back %s: %s", savepoint_name, type(e).__name__)
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
            if log_errors:
                logger.debug(
                    "[SAVEPOINT] Rollback failed for %s: %s",
                    savepoint_name,
                    type(rollback_err).__name__,
                )
        if fallback_value is not None:
            raise
