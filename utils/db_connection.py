#!/usr/bin/env python3
"""
Unified database connection factory with connection pool monitoring.

Centralizes all psycopg2.connect() calls to a single source.
Handles retries, pooling, proper credential fallback, and connection tracking.
"""

import psycopg2
import logging
import socket
import os
import subprocess
import re

from config.credential_manager import get_db_config

logger = logging.getLogger(__name__)

def _sanitize_error(error: Exception, sensitive_value: str = '') -> str:
    """Sanitize error messages to prevent credential leakage in logs.

    Removes known credential patterns and sensitive values before logging.
    """
    error_str = str(error)
    if sensitive_value:
        error_str = error_str.replace(sensitive_value, '***')
    error_str = re.sub(r'password["\']?\s*[:=]\s*["\']?[^"\'\s,)]+', 'password=***', error_str, flags=re.IGNORECASE)
    error_str = re.sub(r'PGPASSWORD["\']?\s*[:=]\s*["\']?[^"\'\s,)]+', 'PGPASSWORD=***', error_str, flags=re.IGNORECASE)
    error_str = re.sub(r'user["\']?\s*[:=]\s*["\']?[^"\'\s,)]+', 'user=***', error_str, flags=re.IGNORECASE)
    return error_str

# Import connection monitor - integrates pool health tracking
try:
    from algo.algo_connection_monitor import on_connect, on_disconnect
except ImportError as e:
    # CRITICAL: Connection monitor unavailable — pool health tracking disabled.
    # Log as error, not silent fallback. This masks connection pool exhaustion issues.
    logger.error(f"Connection monitor import failed: {e} — pool health tracking unavailable")
    def on_connect():
        logger.debug("[FALLBACK] on_connect called but monitor not loaded")
    def on_disconnect():
        logger.debug("[FALLBACK] on_disconnect called but monitor not loaded")

class TrackedConnection:
    """Wraps psycopg2 connection to track pool utilization."""

    def __init__(self, conn):
        self._conn = conn
        on_connect()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)

    def close(self):
        on_disconnect()
        return self._conn.close()

def get_db_connection(max_retries: int = 5, timeout: int = 10, debug: bool = False):
    """Get a database connection with retries and proper credential fallback.

    Args:
        max_retries: Number of retry attempts on transient errors (increased from 3 to 5 for connection pool congestion)
                     Note: max_retries=0 means 1 attempt (0 retries after first), max_retries=1 means 2 attempts, etc.
        timeout: Connection timeout in seconds
        debug: If True, log detailed connection attempts

    Returns:
        A psycopg2 connection object

    Raises:
        psycopg2.OperationalError: If connection fails after retries
    """
    db_config = get_db_config()

    if not all([db_config.get('host'), db_config.get('user'), db_config.get('password')]):
        raise psycopg2.OperationalError("Missing required database configuration")

    last_error = None
    # max_retries=0 means 1 total attempt (no retries), so range should be (1, 2)
    # max_retries=1 means 2 total attempts (1 retry), so range should be (1, 3)
    password = db_config.get('password', '')
    for attempt in range(1, max_retries + 2):
        try:
            if debug:
                logger.debug(f"[DB_CONNECT] Attempt {attempt}/{max_retries + 1}")

            conn = psycopg2.connect(
                host=db_config['host'],
                port=int(db_config['port']),
                database=db_config['database'],
                user=db_config['user'],
                password=password,
                connect_timeout=timeout
            )

            if debug:
                logger.debug(f"[DB_CONNECT] Connected successfully on attempt {attempt}")

            return conn
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt <= max_retries:
                import time
                wait_time = min(2 ** (attempt - 1), 10)  # Exponential backoff, max 10s
                if debug:
                    safe_error = _sanitize_error(e, password)
                    logger.debug(f"[DB_CONNECT] Connection failed (attempt {attempt}): {safe_error[:100]}, retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                if debug:
                    safe_error = _sanitize_error(e, password)
                    logger.error(f"[DB_CONNECT] Connection failed after {max_retries + 1} attempts: {safe_error}")

    raise last_error if last_error else psycopg2.OperationalError("Failed to connect to database")
