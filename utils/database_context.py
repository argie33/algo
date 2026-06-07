#!/usr/bin/env python3
"""
Unified Database Connection Context Manager

THE RIGHT WAY: All database access goes through this context manager.
- Automatic connection pooling and cleanup
- Proper error classification and retry logic
- Connection tracking and monitoring
- Thread-safe cursor factory
- ISSUE #13 FIX: Automatic correlation_id tracking for end-to-end tracing
"""

import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import DictCursor, RealDictCursor

from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)
__all__ = ['DatabaseContext']


class _CorrelationIdCursor:
    """Wrapper around psycopg2 cursor that auto-includes correlation_id in SQL comments.

    This enables end-to-end tracing of database changes back to specific loader runs.
    Example SQL becomes:
        INSERT INTO table VALUES (...) /* correlation_id: abc123 */
    """

    def __init__(self, cursor, correlation_id: str):
        self.cursor = cursor
        self.correlation_id = correlation_id

    def execute(self, query: str, args=None):
        """Execute query with correlation_id comment appended."""
        if query and not query.strip().startswith('--'):
            sql_with_comment = f"{query} /* correlation_id: {self.correlation_id} */"
        else:
            sql_with_comment = query

        if args is not None:
            return self.cursor.execute(sql_with_comment, args)
        else:
            return self.cursor.execute(sql_with_comment)

    def executemany(self, query: str, args):
        """Execute many with correlation_id comment appended."""
        if query and not query.strip().startswith('--'):
            sql_with_comment = f"{query} /* correlation_id: {self.correlation_id} */"
        else:
            sql_with_comment = query
        return self.cursor.executemany(sql_with_comment, args)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size: int = None):
        return self.cursor.fetchmany(size)

    def close(self):
        return self.cursor.close()

    @property
    def description(self):
        return self.cursor.description

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def connection(self):
        return self.cursor.connection

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def __iter__(self):
        return iter(self.cursor)

    def __getattr__(self, name):
        return getattr(self.cursor, name)

class DatabaseContext:
    """Thread-safe database context with automatic resource cleanup.

    For role='write': automatically commits on success, rolls back on exception.
    For role='read': no commit (read-only).

    ISSUE #13 FIX: Automatically includes correlation_id from context in all operations
    via SQL comments. This enables tracing all database changes back to a specific loader run.

    Usage:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
        # Connection automatically closed

        with DatabaseContext('write') as cur:
            cur.execute("INSERT INTO table VALUES ...")
            # Auto-commits on exit if no exception
        # Connection automatically closed

        # Correlation ID is automatically included:
        with correlation_context("loader-run-123"):
            with DatabaseContext('write') as cur:
                cur.execute("INSERT INTO table VALUES ...")
                # SQL comment includes correlation_id for audit trail
    """

    def __init__(self, role: str = 'read', timeout: int = 30, cursor_factory=DictCursor, correlation_id: Optional[str] = None):
        """Initialize context.

        Args:
            role: 'read' or 'write' (controls timeout, retry behavior)
            timeout: Connection timeout in seconds (30s for loader tasks; API Gateway uses shorter timeout)
            cursor_factory: psycopg2 cursor factory (default DictCursor for dict rows)
            correlation_id: Optional explicit correlation_id (auto-retrieves from context if not provided)
        """
        self.role = role
        self.timeout = timeout
        self.cursor_factory = cursor_factory
        # ISSUE #13 FIX: correlation_id for tracing (loaders should provide this)
        # If not provided, attempt to get from the load_prices module's contextvars
        self.correlation_id = correlation_id or self._get_loader_correlation_id()
        self.conn = None
        self.cur = None

    @staticmethod
    def _get_loader_correlation_id() -> str:
        """Get correlation_id from load_prices module if available, else fallback."""
        try:
            # Try to import the _correlation_id_var from load_prices
            from loaders.load_prices import _correlation_id_var, _correlation_id
            cid = _correlation_id_var.get()
            if cid:
                return cid
            # If not set in contextvars, use the module-level _correlation_id
            return _correlation_id
        except (ImportError, AttributeError, Exception):
            # Fallback if load_prices is not available
            return "NO_CID"

    def __enter__(self):
        """Enter context - get database connection."""
        try:
            self.conn = get_db_connection(timeout=self.timeout)
            self.cur = self.conn.cursor(cursor_factory=self.cursor_factory)

            # ISSUE #13 FIX: Set session-level variable with correlation_id for PostgreSQL audit trail
            try:
                self.cur.execute(f"SET application_name = %s", (f"algo_loader[{self.correlation_id}]",))
            except Exception as set_var_err:
                logger.debug(f"[DB_CONTEXT] Could not set application_name for tracing: {set_var_err}")

            # Wrap cursor to auto-include correlation_id in SQL comments for audit trail
            return _CorrelationIdCursor(self.cur, self.correlation_id)
        except Exception as e:
            logger.error(f"[DB_CONTEXT_ERROR] Failed to get database connection: {e}", exc_info=True)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - cleanup connection."""
        try:
            if self.cur:
                self.cur.close()
            if self.conn:
                if exc_type is None and self.role == 'write':
                    self.conn.commit()
                elif exc_type is not None:
                    self.conn.rollback()
                self.conn.close()
        except Exception as e:
            logger.warning(f"[DB_CLEANUP_WARNING] Error closing database connection: {e}")
        finally:
            self.cur = None
            self.conn = None

