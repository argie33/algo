#!/usr/bin/env python3
"""
Unified Database Connection Context Manager

THE RIGHT WAY: All database access goes through this context manager.
- Automatic connection pooling and cleanup
- Proper error classification and retry logic
- Connection tracking and monitoring
- Thread-safe cursor factory
- Optional correlation_id tracking for end-to-end audit trails (loaders only)
"""

import logging
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor

from utils.db.connection import get_db_connection
from utils.db.pooled_context_var import get_pooled_connection
from utils.db.structured_logging import StructuredDBLogger

logger = logging.getLogger(__name__)
__all__ = ["DatabaseContext"]


class _ErrorLoggedCursor:
    """Wraps cursor to log structured errors on query failures.

    Captures:
    - The SQL query that failed
    - Query parameters
    - Error type and message
    - Operational context (extracted from params if possible)
    """

    def __init__(self, cursor, operation_name: str = "db_operation"):
        self.cursor = cursor
        self.operation_name = operation_name
        self.last_query: str | None = None
        self.last_args: Any | None = None

    def execute(self, query: str, args=None):
        """Execute query with error logging."""
        self.last_query = query
        self.last_args = args
        try:
            return self.cursor.execute(query, args)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            context = StructuredDBLogger.extract_context_from_params(args)
            StructuredDBLogger.log_db_error(
                operation_name=self.operation_name,
                query=query,
                params=args,
                error=e,
                context=context if context else None,
            )
            raise

    def executemany(self, query: str, args):
        """Execute many with error logging."""
        self.last_query = query
        self.last_args = args
        try:
            return self.cursor.executemany(query, args)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            context = StructuredDBLogger.extract_context_from_params(args)
            StructuredDBLogger.log_db_error(
                operation_name=self.operation_name,
                query=query,
                params=args,
                error=e,
                context=context if context else None,
            )
            raise

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size: int | None = None):
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


class _CorrelationIdCursor:
    """Wraps cursor to auto-include correlation_id in SQL comments for audit trails.

    Only used when correlation_id is provided. Enables tracing database changes
    back to specific loader runs.
    """

    def __init__(self, cursor, correlation_id: str):
        self.cursor = cursor
        self.correlation_id = correlation_id

    def execute(self, query: str, args=None):
        """Execute with correlation_id comment appended."""
        # For psycopg2.sql objects with arguments, don't convert to string
        # (breaks parameter binding). Just pass the object directly.
        if hasattr(query, "as_string") and args is not None:
            return self.cursor.execute(query, args)

        # For string queries or parameterless SQL objects, append comment
        query_str = query.as_string(self.cursor) if hasattr(query, "as_string") else str(query or "")
        if query_str and not query_str.strip().startswith("--"):
            query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"

        if not hasattr(query, "as_string") and args is None:
            return self.cursor.execute(query_str)
        return self.cursor.execute(query_str, args)

    def executemany(self, query: str, args):
        """Execute many with correlation_id comment appended."""
        query_str = query.as_string(self.cursor) if hasattr(query, "as_string") else str(query or "")
        if query_str and not query_str.strip().startswith("--"):
            query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"
        return self.cursor.executemany(query_str, args)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size: int | None = None):
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
    """Thread-safe database context with optional correlation_id tracking.

    SPLIT USAGE (DO NOT CONSOLIDATE INCORRECTLY):

    1. LOADERS (utils imports):
       - Use: from utils.db import DatabaseContext
       - Needs: correlation_id tracking for audit trails via SQL comments
       - Timeout: 30s (longer-running batch operations)
       - Example: load_prices.py, load_technical_data_daily.py, etc.

    2. REST API (api_utils re-exports):
       - Use: from api_utils.database_context import DatabaseContext
       - Needs: No correlation_id tracking (per-request context, not batch)
       - Timeout: 20s (API Gateway limit)
       - Example: lambda/api/lambda_function.py

    Why separate exports?
    - Loaders auto-retrieve correlation_id from context and inject into SQL comments
    - API calls explicitly pass None to skip tracing (no batch context)
    - Different timeout defaults reflect operational patterns

    Usage (loaders - auto correlation_id from context):
        with DatabaseContext('write') as cur:
            cur.execute("INSERT ...")  # SQL includes correlation_id comment
            # Auto-commits on exit if no exception

    Usage (API - no correlation_id):
        with DatabaseContext('read', timeout=20) as cur:
            cur.execute("SELECT ...")  # No tracing overhead
            rows = cur.fetchall()
    """

    def __init__(
        self,
        role: str = "read",
        timeout: int = 30,
        cursor_factory=DictCursor,
        correlation_id: str | None = None,
        enable_correlation_tracking: bool = True,
    ):
        """Initialize context.

        Args:
            role: 'read' or 'write' (controls commit/rollback behavior)
            timeout: Connection timeout in seconds
            cursor_factory: psycopg2 cursor factory
            correlation_id: Explicit correlation_id. If None and
                enable_correlation_tracking=True, tries to auto-retrieve from
                context (loaders only).
            enable_correlation_tracking: If True, auto-retrieve correlation_id
                from context if not explicitly provided. Set False for API.
        """
        self.role = role
        self.timeout = timeout
        self.cursor_factory = cursor_factory
        self.enable_correlation_tracking = enable_correlation_tracking
        self.correlation_id = correlation_id
        if correlation_id is None and enable_correlation_tracking:
            self.correlation_id = self._get_loader_correlation_id()
        self.conn: Any = None
        self.cur: Any = None
        self._externally_managed = False  # Track if connection is from pooled context

    @staticmethod
    def _get_loader_correlation_id() -> str | None:
        """Auto-retrieve correlation_id from context (loaders only)."""
        try:
            from utils.infrastructure import get_correlation_id

            cid = get_correlation_id()
            return cid if cid else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to get correlation ID for tracing: {e}")
            return None

    def __enter__(self):
        """Enter context - get database connection.

        OPTIMIZATION: Check for a pooled connection first (set by OptimalLoader).
        If available, reuse it. Otherwise, acquire from pool normally.
        This reduces connection churn from 5-10 creates per loader to 1 create.
        """
        try:
            # OPTIMIZATION: Try to reuse a pooled connection (held by OptimalLoader)
            pooled_conn = get_pooled_connection()
            if pooled_conn is not None:
                self.conn = pooled_conn
                self._externally_managed = True
                logger.debug("[DB_CONTEXT] Reusing pooled connection from OptimalLoader")
            else:
                # Normal flow: acquire new connection from pool
                self.conn = get_db_connection(timeout=self.timeout)
                self._externally_managed = False

            self.cur = self.conn.cursor(cursor_factory=self.cursor_factory)

            # Set application_name for PostgreSQL audit log (loaders only)
            if self.correlation_id:
                try:
                    self.cur.execute(
                        "SET application_name = %s",
                        (f"algo_loader[{self.correlation_id}]",),
                    )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    msg = f"Unexpected error: {e}"
                    raise RuntimeError(msg) from e

            # Wrap cursor with error logging + correlation_id tracing
            if self.correlation_id:
                # First wrap with correlation ID injection
                cor_cursor = _CorrelationIdCursor(self.cur, self.correlation_id)
                # Then wrap with error logging
                op_name = "loader_db_operation"
                return _ErrorLoggedCursor(cor_cursor, operation_name=op_name)

            # Just error logging, no correlation ID
            return _ErrorLoggedCursor(self.cur, operation_name="db_operation")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            context = {"error_type": type(e).__name__, "timeout": self.timeout}
            logger.error(
                f"[DB_CONTEXT_ERROR] Failed to get database connection: {e}",
                exc_info=True,
            )
            StructuredDBLogger.log_db_error(
                operation_name="connection_acquisition",
                query="<connection>",
                error=e,
                context=context,
            )
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - cleanup connection.

        OPTIMIZATION: If connection is externally managed (from pooled context),
        don't close it - let OptimalLoader manage its lifecycle.

        Guarantees: Rollback is ALWAYS called on exception to prevent
        "transaction is aborted" state from poisoning the connection pool.
        """
        try:
            # Always try to close cursor, but don't let cursor errors prevent rollback
            if self.cur:
                try:
                    self.cur.close()
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.warning(f"[DB_CLEANUP_WARNING] Error closing cursor: {e}")
        finally:
            try:
                if self.conn:
                    if not self._externally_managed:
                        # Only close connections we acquired
                        if exc_type is None and self.role == "write":
                            self.conn.commit()
                        else:
                            # Always rollback for:
                            # - Any exception (clears aborted transaction)
                            # - Read connections (clears internally-caught failures)
                            self.conn.rollback()
                        self.conn.close()
                    else:
                        # Still commit/rollback, but don't close the connection
                        if exc_type is None and self.role == "write":
                            self.conn.commit()
                        else:
                            self.conn.rollback()
                        logger.debug("[DB_CONTEXT] Not closing externally-managed connection")
            except Exception as e:
                logger.warning(f"[DB_CLEANUP_WARNING] Error in database context cleanup: {e}")
            finally:
                self.cur = None
                if not self._externally_managed:
                    self.conn = None
