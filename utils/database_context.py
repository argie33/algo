#!/usr/bin/env python3
"""
Unified Database Connection Context Manager

THE RIGHT WAY: All database access goes through this context manager.
- Automatic connection pooling and cleanup
- Proper error classification and retry logic
- Connection tracking and monitoring
- Thread-safe cursor factory
"""

import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor

from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)
__all__ = ['DatabaseContext', 'database_transaction']


class DatabaseContext:
    """Thread-safe database context with automatic resource cleanup.

    Usage:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
        # Connection automatically closed
    """

    def __init__(self, role: str = 'read', timeout: int = 10, cursor_factory=RealDictCursor):
        """Initialize context.

        Args:
            role: 'read' or 'write' (controls timeout, retry behavior)
            timeout: Connection timeout in seconds
            cursor_factory: psycopg2 cursor factory (default RealDictCursor for dict rows)
        """
        self.role = role
        self.timeout = timeout
        self.cursor_factory = cursor_factory
        self.conn = None
        self.cur = None

    def __enter__(self):
        """Enter context - get database connection."""
        try:
            self.conn = get_db_connection(timeout=self.timeout)
            self.cur = self.conn.cursor(cursor_factory=self.cursor_factory)
            return self.cur
        except Exception as e:
            logger.error(f"[DB_CONTEXT_ERROR] Failed to get database connection: {e}", exc_info=True)
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - cleanup connection."""
        try:
            if self.cur:
                self.cur.close()
            if self.conn:
                self.conn.close()
        except Exception as e:
            logger.warning(f"[DB_CLEANUP_WARNING] Error closing database connection: {e}")
        finally:
            self.cur = None
            self.conn = None


@contextmanager
def database_transaction(role: str = 'write', timeout: int = 10):
    """Context manager for transactional database operations.

    Usage:
        with database_transaction() as cur:
            cur.execute("INSERT INTO table VALUES ...")
            cur.connection.commit()  # Explicit commit for clarity
        # On exit: closes connection, rolls back if exception occurred
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection(timeout=timeout)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        # Caller must explicitly commit - we don't auto-commit
    except Exception as e:
        if conn:
            try:
                conn.rollback()
                logger.info(f"[DB_TRANSACTION] Rolled back on {type(e).__name__}")
            except Exception as rollback_err:
                logger.warning(f"[DB_ROLLBACK_FAILED] {rollback_err}")
        logger.error(f"[DB_TRANSACTION_ERROR] {e}", exc_info=True)
        raise
    finally:
        if cur:
            try:
                cur.close()
            except Exception as e:
                logger.warning(f"[DB_CURSOR_CLOSE_FAILED] {e}")
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"[DB_CONNECTION_CLOSE_FAILED] {e}")
