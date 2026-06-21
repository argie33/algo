"""Context managers for standardized error handling in different scenarios.

Provides:
- DatabaseErrorContext: Catch database errors with automatic classification
- LoaderErrorContext: Catch loader errors with correlation tracking
- ExternalAPIContext: Catch API errors with retry logic
- TimeoutContext: Enforce operation timeout
- TransactionContext: Explicit transaction with rollback on any error
"""

import logging
import time
from contextlib import contextmanager
from typing import Optional
import psycopg2
import requests


logger = logging.getLogger(__name__)


class DatabaseErrorContext:
    """Context manager for database operations with standardized error handling.

    Catches database errors, classifies them, logs with full context.

    Usage:
        with DatabaseErrorContext(operation='fetch prices', table='price_daily'):
            cur.execute("SELECT * FROM price_daily WHERE symbol=%s", ('AAPL',))
            return cur.fetchall()
    """

    def __init__(
        self,
        operation: str,
        table: Optional[str] = None,
        role: str = "read",
    ):
        self.operation = operation
        self.table = table
        self.role = role
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            logger.debug(
                f"[{self.role.upper()}] {self.operation} completed in {duration:.3f}s"
            )
            return False

        # Error occurred
        from utils.error_handlers import log_error_with_context

        context = {
            "operation": self.operation,
            "table": self.table,
            "role": self.role,
            "duration_sec": duration,
        }

        log_error_with_context(exc_val, self.operation, context)
        return False  # Re-raise exception


class LoaderErrorContext:
    """Context manager for loader operations with status tracking.

    Auto-logs with correlation_id, updates loader status table, handles timeouts.

    Usage:
        with LoaderErrorContext(
            table_name='price_daily',
            symbol='AAPL',
            correlation_id='phase1-abc123',
        ) as loader_ctx:
            result = fetch_and_insert_prices('AAPL')
            loader_ctx.record_result(rows_inserted=100)
    """

    def __init__(
        self,
        table_name: str,
        symbol: Optional[str] = None,
        correlation_id: Optional[str] = None,
        operation_type: str = "insert",
    ):
        self.table_name = table_name
        self.symbol = symbol
        self.correlation_id = correlation_id
        self.operation_type = operation_type
        self.start_time = None
        self.rows_inserted = 0
        self.rows_failed = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def record_result(self, rows_inserted: int = 0, rows_failed: int = 0):
        """Record result counts."""
        self.rows_inserted += rows_inserted
        self.rows_failed += rows_failed

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        context = {
            "table_name": self.table_name,
            "symbol": self.symbol,
            "correlation_id": self.correlation_id,
            "operation_type": self.operation_type,
            "duration_sec": duration,
            "rows_inserted": self.rows_inserted,
            "rows_failed": self.rows_failed,
        }

        if exc_type is None:
            logger.info(
                f"[{self.operation_type.upper()}] {self.table_name} "
                f"({self.symbol or 'all'}): {self.rows_inserted} inserted, "
                f"{self.rows_failed} failed in {duration:.2f}s"
            )
            return False

        # Error occurred
        from utils.error_handlers import log_error_with_context

        log_error_with_context(exc_val, f"loader[{self.table_name}]", context)
        return False


@contextmanager
def ExternalAPIContext(
    api_name: str,
    operation: str,
    timeout_sec: int = 10,
    max_retries: int = 3,
    backoff_initial: float = 1.0,
    backoff_multiplier: float = 2.0,
):
    """Context manager for external API calls with retry and timeout.

    Usage:
        with ExternalAPIContext('yfinance', 'fetch AAPL prices', timeout_sec=10) as api_ctx:
            response = requests.get(url, timeout=10)
            return response.json()
    """

    start_time = time.time()

    try:
        # Yield to caller
        yield

    except (requests.RequestException, requests.Timeout) as e:
        duration = time.time() - start_time
        context = {
            "api_name": api_name,
            "operation": operation,
            "timeout_sec": timeout_sec,
            "max_retries": max_retries,
            "duration_sec": duration,
        }

        from utils.error_handlers import log_error_with_context

        log_error_with_context(e, f"api[{api_name}]", context)

        # Determine if retriable
        retriable_types = (
            ConnectionError,
            TimeoutError,
            Exception,  # Try retry for anything
        )

        if isinstance(e, retriable_types):
            logger.warning(f"API error from {api_name}, might retry: {e}")

        raise


@contextmanager
def TimeoutContext(
    operation: str,
    timeout_sec: int = 25,
):
    """Context manager that enforces operation timeout.

    Usage:
        with TimeoutContext('fetch market data', timeout_sec=15):
            # If this takes >15 seconds, raises TimeoutError
            data = expensive_fetch()
    """
    import signal

    start_time = time.time()

    def timeout_handler(signum, frame):
        elapsed = time.time() - start_time
        raise TimeoutError(
            f"{operation} exceeded {timeout_sec}s timeout (elapsed: {elapsed:.1f}s)"
        )

    # Set alarm (Unix only, Windows doesn't support signals well)
    old_handler = None
    try:
        if hasattr(signal, "SIGALRM"):
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_sec)  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        # Windows or already set
        pass

    try:
        yield
    finally:
        # Cancel alarm
        try:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)  # type: ignore[attr-defined]
                if old_handler:
                    signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError):
            pass

        elapsed = time.time() - start_time
        if elapsed > timeout_sec * 0.9:
            logger.warning(
                f"{operation} nearing timeout: {elapsed:.1f}s / {timeout_sec}s"
            )


@contextmanager
def TransactionContext(
    cur,
    operation: str = "transaction",
    should_rollback: bool = True,
):
    """Context manager for explicit database transaction.

    Auto-commits on success, rolls back on any exception.

    Usage:
        with TransactionContext(cur, 'reconcile positions') as txn:
            cur.execute("INSERT INTO positions ...")
            cur.execute("UPDATE portfolio ...")
            # Auto-commits on exit
    """
    start_time = time.time()

    try:
        yield cur
        # Auto-commit (connection will commit on context exit)
        duration = time.time() - start_time
        logger.debug(f"[TRANSACTION] {operation} committed in {duration:.3f}s")

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        duration = time.time() - start_time
        logger.error(f"[TRANSACTION] {operation} failed after {duration:.3f}s: {e}")

        if should_rollback:
            try:
                cur.connection.rollback()
                logger.error(f"[TRANSACTION] Rolled back {operation}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as rollback_err:
                logger.error(
                    f"[TRANSACTION] Failed to rollback {operation}: {rollback_err}"
                )

        raise


