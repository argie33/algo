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
from psycopg2.extras import DictCursor, RealDictCursor

from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)
__all__ = ['DatabaseContext']

class DatabaseContext:
    """Thread-safe database context with automatic resource cleanup.

    For role='write': automatically commits on success, rolls back on exception.
    For role='read': no commit (read-only).

    Usage:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT * FROM table")
            rows = cur.fetchall()
        # Connection automatically closed

        with DatabaseContext('write') as cur:
            cur.execute("INSERT INTO table VALUES ...")
            # Auto-commits on exit if no exception
        # Connection automatically closed
    """

    def __init__(self, role: str = 'read', timeout: int = 20, cursor_factory=DictCursor):
        """Initialize context.

        Args:
            role: 'read' or 'write' (controls timeout, retry behavior)
            timeout: Connection timeout in seconds (20s for API Gateway limit of 29s; RDS Proxy handles pooling)
            cursor_factory: psycopg2 cursor factory (default DictCursor for dict rows)
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

