#!/usr/bin/env python3
"""Database context for use with pre-acquired pooled connections.

Works with PooledConnectionManager to provide cursors from an existing connection.
Unlike DatabaseContext, this does NOT manage connection lifecycle - the connection
is already acquired and managed elsewhere.

Usage:
    manager = PooledConnectionManager('my_loader')
    conn = manager.acquire()
    try:
        with PooledDatabaseContext(conn) as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()
        # Connection still open, can use again
        with PooledDatabaseContext(conn) as cur:
            cur.execute("INSERT ...")
    finally:
        manager.release()
"""

import logging

import psycopg2
from psycopg2.extras import DictCursor


logger = logging.getLogger(__name__)


class PooledDatabaseContext:
    """Cursor context for pre-acquired pooled connections.

    CRITICAL: Does NOT close the connection on exit. That's managed by PooledConnectionManager.
    Closing the cursor is optional (psycopg2 recommends it for cleanup but it's not required).
    """

    def __init__(
        self,
        connection: psycopg2.extensions.connection,
        cursor_factory=DictCursor,
        close_cursor_on_exit: bool = True,
    ):
        """Initialize context with existing connection.

        Args:
            connection: Pre-acquired psycopg2 connection (from PooledConnectionManager)
            cursor_factory: Cursor type (default DictCursor for column names)
            close_cursor_on_exit: If True, close cursor on exit (recommended). Never closes connection.
        """
        self.connection = connection
        self.cursor_factory = cursor_factory
        self.close_cursor_on_exit = close_cursor_on_exit
        self.cursor = None

    def __enter__(self):
        """Create cursor from pre-acquired connection."""
        try:
            self.cursor = self.connection.cursor(cursor_factory=self.cursor_factory)
            return self.cursor
        except Exception as e:
            logger.error(
                f"[POOLED_CONTEXT] Failed to create cursor: {e}", exc_info=True
            )
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit - close cursor but NOT connection.

        Connection lifecycle is managed by PooledConnectionManager.
        """
        try:
            if self.cursor and self.close_cursor_on_exit:
                self.cursor.close()
        except Exception as e:
            logger.warning(f"[POOLED_CONTEXT] Error closing cursor: {e}")

        # Auto-commit on success (if we're in an explicit transaction)
        if exc_type is None:
            try:
                # Check if connection is in autocommit mode
                if not self.connection.autocommit:
                    self.connection.commit()
            except Exception as e:
                logger.warning(f"[POOLED_CONTEXT] Error committing: {e}")
        else:
            # Rollback on exception
            try:
                if not self.connection.autocommit:
                    self.connection.rollback()
            except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e  # Don't suppress exceptions
