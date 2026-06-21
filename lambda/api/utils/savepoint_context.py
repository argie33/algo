"""Context manager for PostgreSQL SAVEPOINT handling with automatic rollback on error."""

import logging
from contextlib import contextmanager

import psycopg2


logger = logging.getLogger(__name__)


@contextmanager
def savepoint_context(cur, savepoint_name: str, fallback_value=None, log_errors=True):
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
        psycopg2.errors.QueryCanceled,
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
    ) as e:
        if log_errors:
            logger.warning(f"[SAVEPOINT] Rolling back {savepoint_name}: {type(e).__name__}")
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        except (psycopg2.OperationalError, psycopg2.DatabaseError) as rollback_err:
            if log_errors:
                logger.debug(f"[SAVEPOINT] Rollback failed for {savepoint_name}: {type(rollback_err).__name__}")
        if fallback_value is not None:
            raise
