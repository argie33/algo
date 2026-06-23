#!/usr/bin/env python3
"""
PostgreSQL Advisory Locks for Data Integrity

Prevents race conditions in concurrent Phase 6/7/8/9 writes using PostgreSQL's
distributed advisory locks. All critical table writes use explicit locking.

Lock ID Assignment (ensures no conflicts):
  2147483647 (used by position_sizer for portfolio snapshots)
  2147483646 (algo_trades)
  2147483645 (algo_positions)
  2147483644 (portfolio_snapshots secondary)
  2147483643 (algo_audit_log)
  2147483642 (algo_metrics_daily)
"""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)

# Advisory lock IDs (non-conflicting, high values to avoid user app locks)
ALGO_TRADES_LOCK_ID = 2147483646
ALGO_POSITIONS_LOCK_ID = 2147483645
ALGO_PORTFOLIO_SNAPSHOTS_LOCK_ID = 2147483647  # Shared with position_sizer
ALGO_AUDIT_LOG_LOCK_ID = 2147483643
ALGO_METRICS_DAILY_LOCK_ID = 2147483642


def acquire_advisory_lock(cursor: Any, lock_id: int, table_name: str = "unknown") -> None:
    """Acquire an advisory lock for a critical table.

    Args:
        cursor: Database cursor from DatabaseContext
        lock_id: Advisory lock ID (see constants above)
        table_name: Human-readable table name for logging

    Raises:
        RuntimeError: If lock cannot be acquired
    """
    try:
        cursor.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        cursor.fetchone()
        logger.debug(f"[LOCK] Acquired advisory lock {lock_id} for {table_name}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Failed to acquire advisory lock for {table_name}: {e}") from e


def release_advisory_lock(cursor: Any, lock_id: int, table_name: str = "unknown") -> None:
    """Release an advisory lock.

    Args:
        cursor: Database cursor from DatabaseContext
        lock_id: Advisory lock ID
        table_name: Human-readable table name for logging

    Raises:
        RuntimeError: If lock release fails (should not happen unless connection is closed)
    """
    try:
        cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        cursor.fetchone()
        logger.debug(f"[LOCK] Released advisory lock {lock_id} for {table_name}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.warning(f"Failed to release advisory lock for {table_name}: {e}")


def with_advisory_lock(cursor: Any, lock_id: int, table_name: str, operation: Any) -> Any:
    """Context-manager style lock with guaranteed release.

    Args:
        cursor: Database cursor from DatabaseContext
        lock_id: Advisory lock ID
        table_name: Human-readable table name for logging
        operation: Callable that performs the write operation

    Returns:
        Result from operation

    Raises:
        RuntimeError: If lock cannot be acquired or operation fails
    """
    acquire_advisory_lock(cursor, lock_id, table_name)
    try:
        return operation(cursor)
    finally:
        release_advisory_lock(cursor, lock_id, table_name)
