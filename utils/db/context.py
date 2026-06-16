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
from typing import Optional
from psycopg2.extras import DictCursor

from utils.db.connection import get_db_connection
from utils.db.pooled_context_var import get_pooled_connection

logger = logging.getLogger(__name__)
__all__ = ["DatabaseContext"]


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
        query_str = (
            query.as_string(self.cursor)
            if hasattr(query, "as_string")
            else str(query or "")
        )
        if query_str and not query_str.strip().startswith("--"):
            query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"
        return (
            self.cursor.execute(query_str)
            if not hasattr(query, "as_string") and args is None
            else self.cursor.execute(query_str, args)
        )

    def executemany(self, query: str, args):
        """Execute many with correlation_id comment appended."""
        query_str = (
            query.as_string(self.cursor)
            if hasattr(query, "as_string")
            else str(query or "")
        )
        if query_str and not query_str.strip().startswith("--"):
            query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"
        return self.cursor.executemany(query_str, args)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def fetchmany(self, size: Optional[int] = None):
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
        correlation_id: Optional[str] = None,
        enable_correlation_tracking: bool = True,
    ):
        """Initialize context.

        Args:
            role: 'read' or 'write' (controls commit/rollback behavior)
            timeout: Connection timeout in seconds
            cursor_factory: psycopg2 cursor factory
            correlation_id: Explicit correlation_id. If None and enable_correlation_tracking=True,
                           tries to auto-retrieve from context (loaders only).
            enable_correlation_tracking: If True, attempts to auto-retrieve correlation_id from context
                                        if not explicitly provided. Set to False for API calls.
        """
        self.role = role
        self.timeout = timeout
        self.cursor_factory = cursor_factory
        self.enable_correlation_tracking = enable_correlation_tracking
        self.correlation_id = correlation_id
        if correlation_id is None and enable_correlation_tracking:
            self.correlation_id = self._get_loader_correlation_id()
        self.conn = None
        self.cur = None
        self._externally_managed = False  # Track if connection is from pooled context

    @staticmethod
    def _get_loader_correlation_id() -> Optional[str]:
        """Auto-retrieve correlation_id from context (loaders only)."""
        try:
            from utils.infrastructure import get_correlation_id  # type: ignore[attr-defined]

            cid = get_correlation_id()
            return cid if cid else None
        except Exception:
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
                logger.debug(
                    "[DB_CONTEXT] Reusing pooled connection from OptimalLoader"
                )
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
                except Exception:
                    pass  # Non-critical; continue without session-level tracking

            # Wrap cursor to auto-inject correlation_id into SQL comments (loaders only)
            if self.correlation_id:
                return _CorrelationIdCursor(self.cur, self.correlation_id)
            return self.cur
        except Exception as e:
            logger.error(
                f"[DB_CONTEXT_ERROR] Failed to get database connection: {e}",
                exc_info=True,
            )
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - cleanup connection.

        OPTIMIZATION: If connection is externally managed (from pooled context),
        don't close it - let OptimalLoader manage its lifecycle.
        """
        try:
            if self.cur:
                self.cur.close()

            if self.conn and not self._externally_managed:
                # Only close connections we acquired (not pooled context connections)
                if exc_type is None and self.role == "write":
                    self.conn.commit()
                else:
                    # Always rollback for:
                    # - Any exception (clears aborted transaction)
                    # - Read connections with no exception (clears any internally-caught
                    #   sub-query failures that left the connection in an aborted state;
                    #   without this, the broken connection goes back to the pool and
                    #   poisons the next request with InFailedSqlTransaction errors)
                    self.conn.rollback()
                self.conn.close()
            elif self.conn and self._externally_managed:
                # Still commit/rollback, but don't close the connection
                if exc_type is None and self.role == "write":
                    self.conn.commit()
                else:
                    self.conn.rollback()
                logger.debug(
                    "[DB_CONTEXT] Not closing externally-managed connection (OptimalLoader will close)"
                )
        except Exception as e:
            logger.warning(
                f"[DB_CLEANUP_WARNING] Error in database context cleanup: {e}"
            )
        finally:
            self.cur = None
            if not self._externally_managed:
                self.conn = None
