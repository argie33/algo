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
from collections.abc import Callable
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

    def __init__(self, cursor: Any, operation_name: str = "db_operation") -> None:
        self.cursor = cursor
        self.operation_name = operation_name
        self.last_query: str | None = None
        self.last_args: Any | None = None

    def execute(self, query: str, args: Any = None) -> Any:
        """Execute query with error logging."""
        self.last_query = query
        self.last_args = args
        try:
            self.cursor.execute(query, args)
            return self
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                context = StructuredDBLogger.extract_context_from_params(args)
                StructuredDBLogger.log_db_error(
                    operation_name=self.operation_name,
                    query=query,
                    params=args,
                    error=e,
                    context=context if context else None,
                )
            except Exception as log_err:
                logger.error(f"[DB_LOGGING] Failed to log error (original error: {e}): {log_err}")
            raise

    def executemany(self, query: str, args: Any) -> Any:
        """Execute many with error logging."""
        self.last_query = query
        self.last_args = args
        try:
            return self.cursor.executemany(query, args)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                context = StructuredDBLogger.extract_context_from_params(args)
                StructuredDBLogger.log_db_error(
                    operation_name=self.operation_name,
                    query=query,
                    params=args,
                    error=e,
                    context=context if context else None,
                )
            except Exception as log_err:
                logger.error(f"[DB_LOGGING] Failed to log error (original error: {e}): {log_err}")
            raise

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> Any:
        return self.cursor.fetchall()

    def fetchmany(self, size: int | None = None) -> Any:
        return self.cursor.fetchmany(size)

    def close(self) -> Any:
        return self.cursor.close()

    @property
    def description(self) -> Any:
        return self.cursor.description

    @property
    def rowcount(self) -> Any:
        return self.cursor.rowcount

    @property
    def connection(self) -> Any:
        return self.cursor.connection

    def __enter__(self) -> "_ErrorLoggedCursor":
        return self

    def __exit__(self, *args: Any) -> Any:
        return self.cursor.__exit__(*args)

    def __iter__(self) -> Any:
        return iter(self.cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.cursor, name)


class _CorrelationIdCursor:
    """Wraps cursor to auto-include correlation_id in SQL comments for audit trails.

    Only used when correlation_id is provided. Enables tracing database changes
    back to specific loader runs.
    """

    def __init__(self, cursor: Any, correlation_id: str) -> None:
        self.cursor = cursor
        self.correlation_id = correlation_id

    def execute(self, query: str, args: Any = None) -> Any:
        """Execute with correlation_id comment appended."""
        # For psycopg2.sql objects with arguments, execute as-is
        # (appending comments to SQL objects breaks parameter binding)
        if hasattr(query, "as_string") and args is not None:
            self.cursor.execute(query, args)
            return self

        # For string queries, append comment ONLY if no parameters
        # (appending to parameterized queries risks breaking placeholder counting)
        if isinstance(query, str) and args is None:
            # Safe to append comment when there are no parameters
            query_str = query
            if query_str and not query_str.strip().startswith("--"):
                query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"
            self.cursor.execute(query_str)
        elif isinstance(query, str) and args is not None:
            # CRITICAL: Don't append comment to parameterized queries
            # The correlation_id comment will be added by database logging (query appears in logs)
            # Appending here breaks parameter placeholder counting in psycopg2
            self.cursor.execute(query, args)
        else:
            # SQL object without as_string method
            self.cursor.execute(query, args) if args is not None else self.cursor.execute(query)
        return self

    def executemany(self, query: str, args: Any) -> Any:
        """Execute many with correlation_id comment appended."""
        query_str = query.as_string(self.cursor) if hasattr(query, "as_string") else str(query or "")
        if query_str and not query_str.strip().startswith("--"):
            query_str = f"{query_str} /* correlation_id: {self.correlation_id} */"
        return self.cursor.executemany(query_str, args)

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> Any:
        return self.cursor.fetchall()

    def fetchmany(self, size: int | None = None) -> Any:
        return self.cursor.fetchmany(size)

    def close(self) -> Any:
        return self.cursor.close()

    @property
    def description(self) -> Any:
        return self.cursor.description

    @property
    def rowcount(self) -> Any:
        return self.cursor.rowcount

    @property
    def connection(self) -> Any:
        return self.cursor.connection

    def __enter__(self) -> "_CorrelationIdCursor":
        return self

    def __exit__(self, *args: Any) -> Any:
        return self.cursor.__exit__(*args)

    def __iter__(self) -> Any:
        return iter(self.cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.cursor, name)


class DatabaseContext:
    """Thread-safe database context with optional correlation_id tracking.

    SPLIT USAGE (DO NOT CONSOLIDATE INCORRECTLY):

    1. LOADERS (utils imports):
       - Use: from utils.db import DatabaseContext
       - Needs: correlation_id tracking for audit trails via SQL comments
       - Timeout: 30s (longer-running batch operations)
       - Example: load_prices.py, load_technical_data_daily.py, load_swing_trader_scores.py, etc.

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
        cursor_factory: Callable[..., Any] = DictCursor,
        correlation_id: str | None = None,
        enable_correlation_tracking: bool = True,
    ) -> None:
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
            cid_result = self._get_loader_correlation_id()
            # Only set correlation_id if it's a string (not a marker dict)
            if isinstance(cid_result, str):
                self.correlation_id = cid_result
            # else: unavailable marker or None, skip tracing
        self.conn: Any = None
        self.cur: Any = None
        self._externally_managed = False  # Track if connection is from pooled context

    @staticmethod
    def _get_loader_correlation_id() -> str | dict[str, Any]:
        """Auto-retrieve correlation_id from context (loaders only).

        Returns:
            - Correlation ID string if available
            - Marker dict if unavailable:
              {
                  'data_unavailable': True,
                  'reason': 'correlation_id_unavailable'
              }
        """
        try:
            from utils.infrastructure import get_correlation_id

            cid: str | None = get_correlation_id()
            if cid:
                return cid
            # Return marker dict if no correlation_id in context (optional tracing)
            logger.debug("Correlation_id unavailable - optional tracing disabled")
            return {"data_unavailable": True, "reason": "correlation_id_unavailable"}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to get correlation ID for tracing: {e}")
            return {"data_unavailable": True, "reason": "correlation_id_fetch_error"}

    def __enter__(self) -> _ErrorLoggedCursor:
        """Enter context - get database connection.

        OPTIMIZATION: Check for a pooled connection first (set by OptimalLoader).
        If available, reuse it. Otherwise, acquire from pool normally.
        This reduces connection churn from 5-10 creates per loader to 1 create.

        ISSUE #10 FIX: Set statement_timeout at connection level to prevent
        long-running queries from blocking other connections.

        ISSUE #13 FIX: Set isolation level for critical reads to prevent dirty reads.
        Risk calculations and position sizing must see consistent data.
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

            # ISSUE #13 FIX: Set isolation level for critical reads
            # Use SERIALIZABLE for critical financial calculations (risk, position sizing)
            # Use READ_COMMITTED for loaders and API reads (higher concurrency)
            # CRITICAL BUG FIX (2026-08-02): set_isolation_level() implicitly commits the current
            # transaction! This was causing all writes via DatabaseContext to be silently rolled back.
            # When __enter__ calls set_isolation_level(), it commits any pending work, then __exit__'s
            # commit() has nothing to commit. By executing SET TRANSACTION instead, we avoid the
            # implicit commit and let the transaction continue normally.
            isolation_level = "SERIALIZABLE" if self.role == "read" and not self.correlation_id else "READ_COMMITTED"
            try:
                # Use SET TRANSACTION instead of set_isolation_level() to avoid implicit commit
                sql_isolation = "SERIALIZABLE" if isolation_level == "SERIALIZABLE" else "READ COMMITTED"
                self.cur.execute(f"SET TRANSACTION ISOLATION LEVEL {sql_isolation}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[DB_CONTEXT] Failed to set isolation level to {isolation_level}: {e}")
                # Don't fail on isolation setting, just log and continue

            # ISSUE #10 FIX: Set statement_timeout at connection level
            # Prevents long-running queries from blocking other connections
            # Use a reasonable default: 15 seconds for most operations, 30s for loaders
            stmt_timeout = 30000 if self.correlation_id else 15000  # milliseconds
            try:
                self.cur.execute(f"SET statement_timeout = {stmt_timeout}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.warning(f"[DB_CONTEXT] Failed to set statement_timeout: {e}")
                # Don't fail on timeout setting, just log and continue

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

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context - cleanup connection.

        CRITICAL FIX (2026-08-02): Re-raise exceptions that occurred inside the with
        block instead of suppressing them. Previously, __exit__ would log and rollback
        on exception but NOT re-raise, causing the exception to be SUPPRESSED. This meant
        database errors were silently ignored and code after the with block would execute
        as if the operation succeeded, causing data loss (e.g., orchestrator_execution_log
        never receives run records, appears empty to dashboards). Now __exit__ returns
        None (default, doesn't suppress exceptions) when cleanup succeeds, allowing the
        original exception to propagate.

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
                            logger.info(
                                f"[DB_CONTEXT] __exit__: COMMITTING write (managed={self._externally_managed}, role={self.role}, exc_type={exc_type})"
                            )
                            self.conn.commit()
                            logger.info("[DB_CONTEXT] __exit__: WRITE COMMIT COMPLETE")
                        else:
                            logger.info(f"[DB_CONTEXT] __exit__: ROLLBACK (role={self.role}, exc_type={exc_type})")
                            self.conn.rollback()
                        self.conn.close()
                    else:
                        # Still commit/rollback, but don't close the connection
                        if exc_type is None and self.role == "write":
                            logger.info(f"[DB_CONTEXT] __exit__: COMMIT (externally-managed, role={self.role})")
                            self.conn.commit()
                            logger.info("[DB_CONTEXT] __exit__: COMMIT COMPLETE (externally-managed)")
                        else:
                            logger.info(f"[DB_CONTEXT] __exit__: ROLLBACK (externally-managed, exc_type={exc_type})")
                            self.conn.rollback()
                        logger.debug("[DB_CONTEXT] Not closing externally-managed connection")
            except Exception as cleanup_err:
                logger.critical(
                    f"[DB_CONTEXT CRITICAL] Commit/rollback failed during cleanup: {cleanup_err}", exc_info=True
                )
                # CRITICAL FIX: Re-raise the cleanup error so caller knows transaction failed
                # Previously this was silently logged and suppressed, causing transactions to
                # appear successful when they actually failed (e.g., trades logged "SUCCEEDED"
                # but constraint violations prevented commit, positions created without trades)
                raise
            finally:
                self.cur = None
                if not self._externally_managed:
                    self.conn = None
        # CRITICAL: Re-raise the exception if one occurred
        # Python's with statement will suppress any exception if __exit__ returns True
        # If we return None or False, the exception propagates
        # If we return True, the exception is suppressed (DO NOT DO THIS)
        # By returning None (explicitly or implicitly), we let the original exception propagate
        # (exception occurred but cleanup succeeded - return None to propagate the exception)

    @staticmethod
    def get_pool_status() -> dict[str, Any]:
        """ISSUE #10 FIX: Monitor connection pool status and log warnings.

        Returns:
            Dict with pool utilization metrics:
            - used: number of connections in use
            - capacity: total pool capacity
            - utilization_pct: percentage of pool in use
        """
        try:
            # Get the default connection pool from get_db_connection
            conn = get_db_connection(timeout=2)
            if hasattr(conn, "pool"):
                # If connection has a pool reference, check utilization
                db_pool = conn.pool
                if hasattr(db_pool, "_pool"):
                    # SimpleConnectionPool or ThreadedConnectionPool
                    available = len(db_pool._pool) if hasattr(db_pool, "_pool") else 0
                    capacity = db_pool._maxconn if hasattr(db_pool, "_maxconn") else 10
                    used = max(0, capacity - available)
                    utilization_pct = (used / capacity * 100) if capacity > 0 else 0

                    status = {
                        "used": used,
                        "capacity": capacity,
                        "utilization_pct": utilization_pct,
                    }

                    # Log warnings for high utilization
                    if utilization_pct > 80:
                        logger.warning(
                            f"[DB_POOL_MONITOR] Connection pool utilization high: "
                            f"{used}/{capacity} ({utilization_pct:.1f}%). "
                            f"Potential connection leak or high concurrent load."
                        )
                    if used >= capacity:
                        logger.error(
                            f"[DB_POOL_MONITOR] Connection pool exhausted: "
                            f"{capacity}/{capacity} connections in use. "
                            f"Queries may be blocked waiting for available connection."
                        )

                    return status
            # Fallback if pool structure is different
            return {"used": 0, "capacity": 10, "utilization_pct": 0, "note": "pool structure not detected"}
        except Exception as e:
            logger.warning(f"[DB_POOL_MONITOR] Could not fetch pool status: {e}")
            return {"error": str(e)}
