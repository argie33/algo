#!/usr/bin/env python3
"""
Unified database connection factory with connection pool monitoring.

Centralizes all psycopg2.connect() calls to a single source.
Handles retries, pooling, proper credential fallback, and connection tracking.
"""

import psycopg2
import logging

from config.credential_helper import get_db_config

logger = logging.getLogger(__name__)

# Import connection monitor - integrates pool health tracking
try:
    from algo.algo_connection_monitor import on_connect, on_disconnect
except ImportError:
    # Fallback if monitor unavailable
    def on_connect():
        pass
    def on_disconnect():
        pass


class TrackedConnection:
    """Wraps psycopg2 connection to track pool utilization."""

    def __init__(self, conn):
        self._conn = conn
        on_connect()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        on_disconnect()
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def get_db_connection(max_retries: int = 3, timeout: int = 5):
    """Get a PostgreSQL connection with automatic retry and credential management.

    Tracks connection pool utilization via connection monitor.

    Args:
        max_retries: Number of connection attempts before failing
        timeout: Connection timeout in seconds

    Returns:
        TrackedConnection: Connected database connection (tracks pool health)

    Raises:
        psycopg2.OperationalError: If connection fails after max retries
    """
    config = get_db_config()
    config["connect_timeout"] = timeout

    last_error = None
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**config)
            logger.debug(f"Database connection established (attempt {attempt + 1})")
            return TrackedConnection(conn)
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt + 1} failed, retrying: {e}")
            else:
                logger.error(f"Failed to connect to database after {max_retries} attempts: {e}")

    raise last_error or psycopg2.OperationalError("Database connection failed")
