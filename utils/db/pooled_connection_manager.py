#!/usr/bin/env python3
"""Pooled connection management for loaders with backpressure and reuse.

Fixes connection pool underutilization by:
1. Acquiring ONE connection per loader at startup (not per operation)
2. Reusing that connection for all database operations in the loader
3. Implementing queue-based backpressure when pool is exhausted
4. Returning connection to pool only when loader completes

This reduces connection churn from ~5-10 creates per loader to 1 create per loader.
With 50 loaders: 250-500 creates/releases per cycle → 50 creates/releases per cycle.
"""

import logging
import threading
import time
from typing import Optional
import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)


class PoolSemaphore:
    """Semaphore-style gating for connection pool availability.

    Prevents 50 loaders from all trying to grab connections simultaneously.
    Instead of raising PoolError when pool exhausted, this queues requests
    with backpressure and timeout.
    """

    def __init__(self, max_concurrent: int = 10, timeout_sec: int = 30):
        """Initialize semaphore.

        Args:
            max_concurrent: Max loaders holding connections simultaneously
            timeout_sec: How long to wait for a slot to open
        """
        self.max_concurrent = max_concurrent
        self.timeout_sec = timeout_sec
        self._sem = threading.Semaphore(max_concurrent)
        self._active_count = 0
        self._lock = threading.Lock()

    def acquire(self, loader_name: str = "unknown", timeout: Optional[int] = None) -> bool:
        """Try to acquire a slot from the pool.

        Args:
            loader_name: Name of loader requesting connection (for logging)
            timeout: Override default timeout in seconds

        Returns:
            True if acquired, False if timeout
        """
        timeout = timeout or self.timeout_sec
        acquired = self._sem.acquire(timeout=timeout)

        if acquired:
            with self._lock:
                self._active_count += 1
            logger.debug(
                f"[POOL_SEMAPHORE] {loader_name} acquired slot "
                f"({self._active_count}/{self.max_concurrent} active)"
            )
        else:
            logger.warning(
                f"[POOL_SEMAPHORE] {loader_name} timeout waiting for connection slot "
                f"({self._active_count}/{self.max_concurrent} active, waited {timeout}s)"
            )

        return acquired

    def release(self, loader_name: str = "unknown"):
        """Release a slot back to the pool."""
        self._sem.release()
        with self._lock:
            self._active_count -= 1
        logger.debug(
            f"[POOL_SEMAPHORE] {loader_name} released slot "
            f"({self._active_count}/{self.max_concurrent} active)"
        )

    def status(self) -> dict:
        """Return current semaphore status."""
        with self._lock:
            return {
                'active_count': self._active_count,
                'max_concurrent': self.max_concurrent,
                'available_slots': self.max_concurrent - self._active_count,
            }


# Global pool semaphore - enforces max concurrent loaders
# Set to 10 to safely support 10 concurrent loaders holding connections,
# with room for 10 more in the SimpleConnectionPool for API/internal use
_pool_semaphore = PoolSemaphore(max_concurrent=10, timeout_sec=30)


class PooledConnectionManager:
    """Manages a single persistent connection for a loader's entire lifecycle.

    Usage:
        manager = PooledConnectionManager('sector_ranking')
        try:
            conn = manager.acquire()  # Get connection for this loader
            # Use conn for all operations in your loader
            cur = conn.cursor()
            cur.execute("SELECT ...")
            # ... more queries with same connection ...
        finally:
            manager.release()  # Return to pool when done

    Benefits vs creating DatabaseContext for each operation:
    - 1 connection per loader run instead of 5-10 creates/closes
    - Backpressure: waits gracefully instead of pool exhaustion crash
    - Connection warmth: reuse same connection, better performance
    - Transaction control: easier to manage multi-step operations
    """

    def __init__(self, loader_name: str, timeout_sec: int = 30):
        """Initialize manager for a specific loader.

        Args:
            loader_name: Name of loader (for logging and tracking)
            timeout_sec: How long to wait for connection availability
        """
        self.loader_name = loader_name
        self.timeout_sec = timeout_sec
        self._conn = None
        self._acquired_at = None
        self._lock = threading.Lock()

    def acquire(self) -> Optional[psycopg2.extensions.connection]:
        """Acquire a connection from the pool for this loader.

        Implements backpressure:
        1. First wait for a semaphore slot (gates max concurrent loaders)
        2. Then acquire from the connection pool
        3. If pool exhausted, retry with exponential backoff

        Returns:
            psycopg2 connection object, or None if failed after timeout

        Raises:
            Exception if connection cannot be acquired
        """
        with self._lock:
            if self._conn is not None:
                raise RuntimeError(f"[{self.loader_name}] Connection already acquired")

        # Step 1: Wait for semaphore slot (rate-gates loader parallelism)
        if not _pool_semaphore.acquire(self.loader_name, timeout=self.timeout_sec):
            raise TimeoutError(
                f"[{self.loader_name}] Timed out waiting for connection pool slot "
                f"(max 10 concurrent loaders, timeout={self.timeout_sec}s)"
            )

        # Step 2: Acquire from pool with exponential backoff
        try:
            from utils.db import get_db_connection
            from utils.db.connection import _get_connection_pool

            pool = _get_connection_pool()
            max_retries = 3

            for attempt in range(1, max_retries + 1):
                try:
                    self._conn = pool.getconn()
                    self._acquired_at = time.time()

                    logger.info(
                        f"[{self.loader_name}] Acquired pooled connection "
                        f"(held for up to {self.timeout_sec}s)"
                    )
                    return self._conn

                except psycopg2.pool.PoolError as e:
                    if attempt < max_retries:
                        wait_time = min(2 ** (attempt - 1), 10)
                        logger.warning(
                            f"[{self.loader_name}] Pool exhausted (attempt {attempt}/{max_retries}), "
                            f"retrying in {wait_time}s: {str(e)[:80]}"
                        )
                        time.sleep(wait_time)
                    else:
                        raise

        except Exception as e:
            # Release semaphore on failure
            _pool_semaphore.release(self.loader_name)
            raise

    def release(self) -> None:
        """Release the connection back to the pool.

        Safe to call multiple times (idempotent).
        """
        with self._lock:
            if self._conn is None:
                logger.debug(f"[{self.loader_name}] Release called but no connection held")
                return

            try:
                from utils.db.connection import _get_connection_pool

                pool = _get_connection_pool()
                held_time = time.time() - self._acquired_at

                try:
                    pool.putconn(self._conn)
                    logger.info(
                        f"[{self.loader_name}] Returned connection to pool "
                        f"(held for {held_time:.1f}s)"
                    )
                except Exception as e:
                    logger.warning(
                        f"[{self.loader_name}] Failed to return connection to pool: {e}, "
                        f"closing instead"
                    )
                    try:
                        self._conn.close()
                    except Exception:
                        pass
            finally:
                self._conn = None
                self._acquired_at = None
                _pool_semaphore.release(self.loader_name)

    def get_connection(self) -> Optional[psycopg2.extensions.connection]:
        """Get the currently-held connection (if any).

        Returns:
            Connection object or None if not currently acquired
        """
        return self._conn

    def is_acquired(self) -> bool:
        """Check if a connection is currently held."""
        return self._conn is not None

    def __enter__(self):
        """Context manager entry."""
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


def get_pool_status() -> dict:
    """Get current pool and semaphore status for monitoring."""
    return {
        'semaphore': _pool_semaphore.status(),
        'max_concurrent_loaders': 10,
        'max_pool_connections': 20,
    }
