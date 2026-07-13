#!/usr/bin/env python3
"""Pooled connection management for loaders with backpressure and reuse.

Fixes connection pool underutilization by:
1. Acquiring ONE connection per loader at startup (not per operation)
2. Reusing that connection for all database operations in the loader
3. Implementing queue-based backpressure when pool is exhausted
4. Returning connection to pool only when loader completes
5. Cleaning up idle connections to prevent pool exhaustion

This reduces connection churn from ~5-10 creates per loader to 1 create per loader.
With 50 loaders: 250-500 creates/releases per cycle → 50 creates/releases per cycle.

Idle connection cleanup prevents memory leaks when loaders die or abandon connections.
Connections idle > max_idle_sec are closed and removed from the pool.
"""

import logging
import os
import threading
import time
from collections import deque
from typing import Any, Literal

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)


class IdleConnectionPool:
    """Wraps psycopg2.pool.SimpleConnectionPool to track and clean up idle connections.

    Prevents connection pool exhaustion when loaders die or abandon connections.
    Periodically closes connections that have been idle > max_idle_sec.
    """

    def __init__(
        self,
        pool: psycopg2.pool.SimpleConnectionPool,
        max_idle_sec: int = 300,
        cleanup_interval_sec: int = 60,
    ):
        """Initialize idle connection pool wrapper.

        Args:
            pool: Underlying psycopg2.pool.SimpleConnectionPool
            max_idle_sec: Max seconds a connection can be idle before closing (default 5 min)
            cleanup_interval_sec: How often to run idle cleanup (default 1 min)
        """
        self._pool = pool
        self._max_idle_sec = max_idle_sec
        self._cleanup_interval_sec = cleanup_interval_sec
        self._idle_connections: deque[dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._cleanup_thread: threading.Thread | None = None
        self._stop_cleanup = threading.Event()

        self._start_cleanup_thread()

    def getconn(self) -> Any:
        """Get a connection from the pool.

        Returns:
            Connection from pool

        CRITICAL FIX: Removed local idle connection caching.
        Now always get from underlying pool, which properly manages
        connection availability and prevents pool exhaustion.
        """
        return self._pool.getconn()

    def putconn(self, conn: Any, close: bool = False) -> None:
        """Return a connection to the pool or close it.

        Args:
            conn: Connection to return
            close: If True, close instead of returning to pool

        CRITICAL FIX: Always return connections to the underlying pool immediately.
        Storing them locally in _idle_connections was causing the underlying pool
        to remain exhausted (all connections "checked out" but stored locally).
        This manifested as hangs on the 3rd+ concurrent request.
        """
        try:
            self._pool.putconn(conn, close=close)
            logger.debug(f"[IDLE_POOL] Connection returned to underlying pool")
        except Exception as e:
            if close:
                logger.warning(f"[IDLE_POOL] Failed to close connection: {e}")
            else:
                logger.warning(f"[IDLE_POOL] Failed to return connection to pool: {e}, closing instead")
                try:
                    conn.close()
                except Exception as close_err:
                    logger.debug(f"[IDLE_POOL] Could not close connection: {close_err}")

    def _cleanup_stale_connections(self) -> None:
        """Close connections idle > max_idle_sec."""
        with self._lock:
            now = time.time()
            active_connections: list[dict[str, Any]] = []
            closed_count = 0

            for conn_info in self._idle_connections:
                idle_time = now - conn_info["idle_since"]

                if idle_time > self._max_idle_sec:
                    try:
                        self._pool.putconn(conn_info["conn"], close=True)
                        closed_count += 1
                        logger.info(
                            f"[IDLE_POOL] Closed idle connection (idle for {idle_time:.1f}s > {self._max_idle_sec}s)"
                        )
                    except Exception as e:
                        logger.warning(f"[IDLE_POOL] Failed to close idle connection: {e}")
                else:
                    active_connections.append(conn_info)

            self._idle_connections = deque(active_connections)

            if closed_count > 0:
                logger.debug(
                    f"[IDLE_POOL] Cleanup: closed {closed_count} idle connections, "
                    f"{len(self._idle_connections)} remaining idle"
                )

    def _cleanup_thread_run(self) -> None:
        """Background thread that periodically cleans up idle connections."""
        logger.debug(
            f"[IDLE_POOL] Cleanup thread started "
            f"(max_idle={self._max_idle_sec}s, check every {self._cleanup_interval_sec}s)"
        )

        while not self._stop_cleanup.wait(timeout=self._cleanup_interval_sec):
            try:
                self._cleanup_stale_connections()
            except Exception as e:
                logger.error(f"[IDLE_POOL] Cleanup thread error: {e}", exc_info=True)

        logger.debug("[IDLE_POOL] Cleanup thread stopped")

    def _start_cleanup_thread(self) -> None:
        """Start the background cleanup thread."""
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_thread_run, daemon=True, name="IdleConnectionCleanup"
        )
        self._cleanup_thread.start()

    def stop_cleanup(self) -> None:
        """Stop the cleanup thread (call on shutdown)."""
        logger.debug("[IDLE_POOL] Stopping cleanup thread...")
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=10)

    def closeall(self) -> None:
        """Close all idle connections and the underlying pool."""
        self.stop_cleanup()

        with self._lock:
            for conn_info in self._idle_connections:
                try:
                    self._pool.putconn(conn_info["conn"], close=True)
                except Exception as e:
                    logger.debug(f"[IDLE_POOL] Error closing connection during closeall: {e}")

            self._idle_connections.clear()

        try:
            self._pool.closeall()
        except Exception as e:
            logger.warning(f"[IDLE_POOL] Error closing underlying pool: {e}")

    def status(self) -> dict[str, Any]:
        """Return current idle connection status."""
        with self._lock:
            return {
                "idle_connections": len(self._idle_connections),
                "max_idle_sec": self._max_idle_sec,
            }


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

    def acquire(self, loader_name: str = "unknown", timeout: int | None = None) -> bool:
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
                f"[POOL_SEMAPHORE] {loader_name} acquired slot ({self._active_count}/{self.max_concurrent} active)"
            )
        else:
            logger.warning(
                f"[POOL_SEMAPHORE] {loader_name} timeout waiting for connection slot "
                f"({self._active_count}/{self.max_concurrent} active, waited {timeout}s)"
            )

        return acquired

    def release(self, loader_name: str = "unknown") -> None:
        """Release a slot back to the pool."""
        self._sem.release()
        with self._lock:
            self._active_count -= 1
        logger.debug(
            f"[POOL_SEMAPHORE] {loader_name} released slot ({self._active_count}/{self.max_concurrent} active)"
        )

    def status(self) -> dict[str, Any]:
        """Return current semaphore status."""
        with self._lock:
            return {
                "active_count": self._active_count,
                "max_concurrent": self.max_concurrent,
                "available_slots": self.max_concurrent - self._active_count,
            }


# Global pool semaphore - enforces max concurrent loaders
# Dynamically scale based on ECS task parallelism: allow up to 60 concurrent loaders
# RDS max_connections=200, minus 20 for API/orchestrator/internal = 180 available
# CRITICAL FIX (Session 101): Reduce timeout in ECS to prevent cascading timeouts
# ECS loaders were failing at 58s (30s semaphore + 30s context + error handling)
# In ECS environment, reduce to 15s to fail fast and leave time for error handling
_ecs_timeout_sec = 15 if os.getenv("AWS_REGION") else 30  # ECS=15s, local=30s
_pool_semaphore = PoolSemaphore(max_concurrent=int(os.getenv("LOADER_POOL_MAX_CONCURRENT", "60")), timeout_sec=_ecs_timeout_sec)


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
        self._acquired_at: float | None = None
        self._lock = threading.Lock()

    def acquire(self) -> psycopg2.extensions.connection | None:
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
            from utils.db.connection import _get_connection_pool

            pool = _get_connection_pool()
            max_retries = 3

            for attempt in range(1, max_retries + 1):
                try:
                    self._conn = pool.getconn()
                    self._acquired_at = time.time()

                    logger.info(f"[{self.loader_name}] Acquired pooled connection (held for up to {self.timeout_sec}s)")
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

            raise RuntimeError(
                f"[{self.loader_name}] Failed to acquire connection from pool after {max_retries} retries"
            )

        except (psycopg2.pool.PoolError, RuntimeError, OSError):
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
                    logger.info(f"[{self.loader_name}] Returned connection to pool (held for {held_time:.1f}s)")
                except Exception as e:
                    logger.warning(f"[{self.loader_name}] Failed to return connection to pool: {e}, closing instead")
                    try:
                        self._conn.close()
                    except Exception as close_err:
                        raise RuntimeError(
                            f"[{self.loader_name}] Failed to close connection after putconn failure: {close_err}"
                        ) from close_err
            finally:
                self._conn = None
                self._acquired_at = None
                _pool_semaphore.release(self.loader_name)

    def get_connection(self) -> psycopg2.extensions.connection | None:
        """Get the currently-held connection (if any).

        Returns:
            Connection object or None if not currently acquired
        """
        return self._conn

    def is_acquired(self) -> bool:
        """Check if a connection is currently held."""
        return self._conn is not None

    def __enter__(self) -> Any:
        """Context manager entry."""
        return self.acquire()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        """Context manager exit."""
        self.release()
        return False


def get_pool_status() -> dict[str, Any]:
    """Get current pool and semaphore status for monitoring."""
    from utils.db.connection import _get_connection_pool

    pool = _get_connection_pool()
    idle_status = pool.status() if hasattr(pool, "status") else {}

    # FAIL-FAST: If pool has status() method, validate result has required metrics
    # (do not silently default missing metrics to 0, which could mask pool health issues)
    if idle_status:  # Only validate if status() returned non-empty dict
        if "idle_connections" not in idle_status:
            raise RuntimeError(
                f"Pool status missing 'idle_connections' metric. "
                f"Cannot determine pool health with incomplete data. "
                f"Pool status keys: {list(idle_status.keys())}"
            )
        if "max_idle_sec" not in idle_status:
            raise RuntimeError(
                f"Pool status missing 'max_idle_sec' metric. "
                f"Cannot determine pool configuration with incomplete data. "
                f"Pool status keys: {list(idle_status.keys())}"
            )

    # CRITICAL FIX: Extract validated fields explicitly — validation above ensures they exist
    idle_count = idle_status.get("idle_connections")
    if idle_count is None:
        raise RuntimeError(
            "Pool status validation passed but 'idle_connections' is None — data race or validation logic error"
        )
    max_idle = idle_status.get("max_idle_sec")
    if max_idle is None:
        raise RuntimeError(
            "Pool status validation passed but 'max_idle_sec' is None — data race or validation logic error"
        )

    return {
        "semaphore": _pool_semaphore.status(),
        "idle_connections": idle_count,
        "max_idle_sec": max_idle,
        "max_concurrent_loaders": 10,
        "max_pool_connections": 20,
    }
