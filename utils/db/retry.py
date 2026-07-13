#!/usr/bin/env python3
"""
Database Operation Retry Helper

Handles transient failures and race conditions in database operations
with exponential backoff. Used for optimistic locking retries when
concurrent updates modify records between read and update.
"""

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

import psycopg2

from utils.db.structured_logging import StructuredDBLogger

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _get_retry_delay(attempt: int, base_delay_ms: int = 100, max_delay_ms: int = 5000) -> float:
    delay_ms = base_delay_ms * (2**attempt)
    delay_ms = min(delay_ms, max_delay_ms)
    return float(delay_ms / 1000.0)


class OptimisticLockRetry:

    @staticmethod
    def retry_on_race_condition(
        operation: Callable[[], bool],
        operation_name: str = "database_operation",
        max_attempts: int = 3,
        base_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        query: str | None = None,
        params: Any | None = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Retry an operation if it fails due to optimistic lock conflict (rowcount==0).

        Pattern Usage:
            ```python
            def do_update():
                # Read current state
                cursor.execute("SELECT quantity FROM positions WHERE id=%s", (pos_id,))
                row = cursor.fetchone()
                current_qty = row[0]

                cursor.execute(
                    "UPDATE positions SET quantity=%s WHERE id=%s AND quantity=%s",
                    (new_qty, pos_id, current_qty)
                )
                return cursor.rowcount > 0

            success = OptimisticLockRetry.retry_on_race_condition(
                do_update,
                operation_name="update_position_quantity",
                query="UPDATE positions SET ...",
                params=(new_qty, pos_id, current_qty),
                context={"position_id": pos_id, "stock_id": "AAPL"}
            )
            ```

        Args:
            operation: Callable returning True on success, False on lock failed
            operation_name: Name for logging
            max_attempts: Maximum retry attempts (default 3)
            base_delay_ms: Initial backoff delay in milliseconds (default 100)
            max_delay_ms: Maximum backoff delay in milliseconds (default 5000)
            query: Optional SQL query for logging context
            params: Optional query parameters for logging context
            context: Optional operational context (position_id, stock_id, etc.)

        Returns: True if operation succeeded, False if failed after all retries

        Raises: Exception if a non-race-condition error occurs
        """
        for attempt in range(max_attempts):
            try:
                success = operation()
                if success:
                    if attempt > 0:
                        msg = f"[Retry] {operation_name} succeeded after {attempt + 1} attempts"
                        logger.info(msg)
                    return True
                # Optimistic lock failed (rowcount == 0), retry
                if attempt < max_attempts - 1:
                    delay = _get_retry_delay(attempt, base_delay_ms, max_delay_ms)
                    StructuredDBLogger.log_retry(
                        operation_name=operation_name,
                        query=query or "<operation>",
                        params=params,
                        error=None,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        context=context,
                    )
                    time.sleep(delay)
            except Exception as e:
                # Non-transient error, fail immediately
                StructuredDBLogger.log_db_error(
                    operation_name=operation_name,
                    query=query or "<operation>",
                    params=params,
                    error=e,
                    context=context,
                    retry_attempt=attempt,
                    max_attempts=max_attempts,
                )
                logger.error(f"[Retry] {operation_name} failed with non-transient error: {e}")
                raise

        # All retries exhausted
        error = RuntimeError("race condition (optimistic lock failed)")
        StructuredDBLogger.log_db_error(
            operation_name=operation_name,
            query=query or "<operation>",
            params=params,
            error=error,
            context=context,
            retry_attempt=max_attempts - 1,
            max_attempts=max_attempts,
        )
        msg = f"[Retry] {operation_name} failed after {max_attempts} attempts"
        logger.error(msg)
        return False

    @staticmethod
    def retry_on_exception(
        operation: Callable[[], T],
        operation_name: str = "database_operation",
        max_attempts: int = 3,
        base_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        should_retry: Callable[[Exception], bool] | None = None,
        query: str | None = None,
        params: Any | None = None,
        context: dict[str, Any] | None = None,
    ) -> T | None:
        """Retry an operation on specific exceptions (e.g., connection timeouts).

        Args:
            operation: Callable that returns result or raises exception
            operation_name: Name for logging
            max_attempts: Maximum retry attempts (default 3)
            base_delay_ms: Initial backoff delay in milliseconds (default 100)
            max_delay_ms: Maximum backoff delay in milliseconds (default 5000)
            should_retry: Callable(Exception) -> bool for exception is retryable
            query: Optional SQL query for logging context
            params: Optional query parameters for logging context
            context: Optional operational context (stock_id, trade_id, etc.)

        Returns: Operation result if successful, None if failed after retries

        Raises: Non-retryable exceptions are raised immediately
        """

        def default_should_retry(e: Exception) -> bool:
            """Retry on connection/timeout errors, not on logic errors."""
            error_type = type(e).__name__
            retryable_types = (
                "OperationalError",  # psycopg2 connection lost
                "InterfaceError",  # psycopg2 connection error
                "TimeoutError",  # Timeout
            )
            return any(retryable_type in error_type for retryable_type in retryable_types)

        if should_retry is None:
            should_retry = default_should_retry

        last_error = None
        for attempt in range(max_attempts):
            try:
                result = operation()
                if attempt > 0:
                    msg = f"[Retry] {operation_name} succeeded after {attempt + 1} attempts"
                    logger.info(msg)
                return result
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                last_error = e
                if not should_retry(e):
                    StructuredDBLogger.log_db_error(
                        operation_name=operation_name,
                        query=query or "<operation>",
                        params=params,
                        error=e,
                        context=context,
                        retry_attempt=attempt,
                        max_attempts=max_attempts,
                    )
                    logger.error(f"[Retry] {operation_name} failed with non-retryable error: {e}")
                    raise

                if attempt < max_attempts - 1:
                    delay = _get_retry_delay(attempt, base_delay_ms, max_delay_ms)
                    StructuredDBLogger.log_retry(
                        operation_name=operation_name,
                        query=query or "<operation>",
                        params=params,
                        error=e,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        delay_seconds=delay,
                        context=context,
                    )
                    time.sleep(delay)

        error_msg = f"[Retry] {operation_name} failed after {max_attempts} attempts: {last_error}"
        StructuredDBLogger.log_db_error(
            operation_name=operation_name,
            query=query or "<operation>",
            params=params,
            error=last_error or RuntimeError(error_msg),
            context=context,
            retry_attempt=max_attempts - 1,
            max_attempts=max_attempts,
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)
