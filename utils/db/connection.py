#!/usr/bin/env python3
"""
Unified database connection factory with connection pool monitoring.

Centralizes all psycopg2.connect() calls to a single source.
Handles retries, pooling, proper credential fallback, and connection tracking.
"""

import psycopg2
import psycopg2.pool
import logging
import socket
import os
import subprocess
import sys
from pathlib import Path
import threading

# Add project root to path for imports to work in both local dev and Lambda
# In Lambda: /var/task is already in path, credential_manager is in /var/task/config/
# In local dev: need to add the project root so config.credential_manager can be found
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)  # algo/lambda/api/utils -> algo/
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try importing with fallback strategies
try:
    from config.credential_manager import get_db_config
except ImportError as import_err:
    # Fallback 1: Direct import from config directory
    try:
        config_path = str(Path(__file__).resolve().parent.parent.parent.parent / 'config')
        if config_path not in sys.path:
            sys.path.insert(0, config_path)
        from credential_manager import get_db_config
    except ImportError:
        # Fallback 2: Environment-based credential loading
        # This allows the API to work even without the credential_manager module
        def get_db_config():
            return {
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT'),
                'user': os.getenv('DB_USER', 'stocks'),
                'password': os.getenv('DB_PASSWORD'),
                'database': os.getenv('DB_NAME', 'stocks'),
            }
        logging.warning("[DB_CONFIG] Using environment-only credential loading (credential_manager module not found)")

logger = logging.getLogger(__name__)

# Connection pool shared across all requests in this Lambda container
_connection_pool = None
_pool_lock = threading.Lock()

# Import connection monitor - integrates pool health tracking
try:
    from algo.monitoring import on_connect, on_disconnect
except ImportError:
    # Fallback if monitor unavailable
    def on_connect():
        pass
    def on_disconnect():
        pass

def _get_connection_pool():
    """Get or create the module-level connection pool (thread-safe).

    Pool size: minconn=2, maxconn=10
    - minconn=2: keeps 2 idle connections warm (cold-start prevention)
    - maxconn=10: limits per-Lambda instance to 10 connections max
    - RDS Proxy multiplexes to actual DB, limits total to 500 connections

    With 50 concurrent Lambdas at max parallelism (10 conn each) = 500 peak = at RDS limit
    Default: Graceful queueing when pool exhausted (blocks until connection available, max 30s)
    """
    global _connection_pool

    if _connection_pool is None:
        with _pool_lock:
            # Double-check pattern to avoid race conditions
            if _connection_pool is None:
                db_config = get_db_config()
                if not all([db_config.get('host'), db_config.get('user'), db_config.get('password')]):
                    raise psycopg2.OperationalError("Missing required database configuration")

                port = db_config.get('port')
                if port is None:
                    raise psycopg2.OperationalError("DB_PORT environment variable is required")
                try:
                    port = int(port)
                except (ValueError, TypeError) as e:
                    raise psycopg2.OperationalError(f"Invalid DB_PORT: {e}")

                try:
                    # RDS Proxy doesn't support command-line options, so don't pass them during connection
                    # Statement timeout is set at RDS parameter group level instead
                    _connection_pool = psycopg2.pool.SimpleConnectionPool(
                        minconn=2,
                        maxconn=10,
                        host=db_config['host'],
                        port=port,
                        database=db_config['database'],
                        user=db_config['user'],
                        password=db_config['password'],
                        connect_timeout=10
                        # Note: Do NOT pass options= parameter to RDS Proxy
                        # RDS Proxy doesn't support command-line options like -c statement_timeout
                        # Statement timeout is configured at the RDS parameter group level instead
                    )
                    logger.info("[DB_POOL] Connection pool initialized (minconn=2, maxconn=10)")
                except psycopg2.Error as e:
                    logger.error(f"[DB_POOL] Failed to create pool: {e}")
                    raise

    return _connection_pool

class TrackedConnection:
    """Wraps psycopg2 connection to track pool utilization and return to pool.

    When closed, returns connection to pool instead of destroying it.
    """

    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool
        on_connect()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        """Return connection to pool (if managed) or close it."""
        on_disconnect()
        if self._pool:
            try:
                self._pool.putconn(self._conn)
            except Exception as e:
                logger.warning(f"[DB_POOL] Failed to return connection to pool: {e}, closing instead")
                try:
                    self._conn.close()
                except Exception as close_err:
                    logger.debug(f"[DB_POOL] Could not close connection: {close_err}")
        else:
            try:
                self._conn.close()
            except Exception as close_err:
                logger.debug(f"[DB_POOL] Could not close connection: {close_err}")

def get_db_connection(max_retries: int = 3, timeout: int = 10, debug: bool = False):
    """Get a database connection from the connection pool with retries.

    Uses module-level SimpleConnectionPool to prevent RDS connection exhaustion.
    Pool is shared across all requests in this Lambda container (warm instances reuse connections).

    Args:
        max_retries: Number of retry attempts on transient errors
        timeout: Pool timeout in seconds (max wait for available connection)
        debug: If True, log detailed connection attempts

    Returns:
        A TrackedConnection wrapping a pooled psycopg2 connection

    Raises:
        psycopg2.OperationalError: If pool exhausted or connection fails after retries
    """
    last_error = None
    pool = _get_connection_pool()

    for attempt in range(1, max_retries + 2):
        try:
            if debug:
                logger.debug(f"[DB_CONNECT] Attempt {attempt}/{max_retries + 1}: getting pooled connection")

            conn = pool.getconn()

            if debug:
                logger.debug(f"[DB_CONNECT] Got connection from pool on attempt {attempt}")

            return TrackedConnection(conn, pool=pool)

        except psycopg2.pool.PoolError as e:
            last_error = e
            if attempt < max_retries:
                import time
                wait_time = min(2 ** (attempt - 1), 10)
                if debug:
                    logger.debug(f"[DB_CONNECT] Pool exhausted (attempt {attempt}): {str(e)[:100]}, retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                if debug:
                    logger.error(f"[DB_CONNECT] Pool exhausted after {max_retries} attempts: {e}")

        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < max_retries:
                import time
                wait_time = min(2 ** (attempt - 1), 10)
                if debug:
                    logger.debug(f"[DB_CONNECT] Connection failed (attempt {attempt}): {str(e)[:100]}, retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                if debug:
                    logger.error(f"[DB_CONNECT] Connection failed after {max_retries} attempts: {e}")

    raise last_error if last_error else psycopg2.OperationalError("Failed to get pooled connection")
