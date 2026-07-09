#!/usr/bin/env python3
"""Improved database error handling to prevent transaction abort cascades.

PostgreSQL aborts the entire transaction when a query fails. This module
provides utilities to:
1. Detect transaction abort errors ("current transaction is aborted")
2. Handle them gracefully with explicit rollback + retry
3. Provide better error context for debugging
"""

import logging
from collections.abc import Callable
from typing import Any, TypeVar

import psycopg2

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_transaction_abort_error(error: Exception) -> bool:
    """Check if error is a transaction abort error.

    PostgreSQL marks transactions as aborted when a query fails, causing
    subsequent queries to fail with specific error messages.
    """
    error_str = str(error).lower()
    abort_indicators = [
        "current transaction is aborted",
        "current transaction has been aborted",
        "transaction is aborted",
    ]
    return any(indicator in error_str for indicator in abort_indicators)


def safe_query(
    cursor: Any,
    query: str,
    args: Any = None,
    operation_name: str = "query",
) -> Any:
    """Execute a query with proper error handling and transaction recovery.

    If transaction is aborted, explicitly rollback before raising.
    This prevents the abort state from poisoning the connection pool.

    Args:
        cursor: Database cursor
        query: SQL query to execute
        args: Query parameters
        operation_name: Name for logging/debugging

    Raises:
        psycopg2 exceptions on failure (after proper cleanup)
    """
    try:
        cursor.execute(query, args)
        return cursor
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Check if this is a transaction abort error
        if is_transaction_abort_error(e):
            logger.error(
                f"[TRANSACTION_ABORT] Detected aborted transaction in {operation_name}. "
                f"Explicitly rolling back to clear abort state. Error: {e}"
            )
            try:
                # Explicitly rollback to clear abort state
                cursor.connection.rollback()
                logger.info("[TRANSACTION_ABORT] Rollback successful, abort state cleared")
            except Exception as rollback_err:
                logger.error(
                    f"[TRANSACTION_ABORT] Failed to rollback: {rollback_err}. "
                    f"Connection may be in inconsistent state."
                )
        raise


def execute_with_savepoint(
    cursor: Any,
    query: str,
    args: Any = None,
    operation_name: str = "query",
) -> Any:
    """Execute a query with savepoint-based rollback on error.

    Allows individual query failures without aborting the entire transaction.
    If query fails, only the savepoint is rolled back, not the whole transaction.

    Args:
        cursor: Database cursor
        query: SQL query to execute
        args: Query parameters
        operation_name: Name for logging/debugging

    Returns:
        cursor on success

    Raises:
        psycopg2 exceptions on failure
    """
    sp_name = f"sp_{operation_name.replace('.', '_')}"
    try:
        # Create savepoint before query
        cursor.execute(f"SAVEPOINT {sp_name}")
        logger.debug(f"[SAVEPOINT] Created {sp_name}")

        # Execute the actual query
        cursor.execute(query, args)
        logger.debug(f"[SAVEPOINT] Query succeeded: {operation_name}")
        return cursor

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        # Rollback to savepoint (not entire transaction)
        logger.warning(
            f"[SAVEPOINT] Query failed in {operation_name}: {e}. "
            f"Rolling back to savepoint {sp_name}"
        )
        try:
            cursor.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            logger.info(f"[SAVEPOINT] Rolled back to {sp_name}, transaction continues")
        except Exception as rollback_err:
            logger.error(
                f"[SAVEPOINT] Failed to rollback to {sp_name}: {rollback_err}. "
                f"Transaction may be aborted."
            )
        raise


def validate_connection_state(cursor: Any) -> bool:
    """Check if connection/transaction is in a valid state.

    Returns:
        True if connection is OK
        False if transaction is aborted or connection is bad
    """
    try:
        # Try a simple query that should always succeed
        cursor.execute("SELECT 1")
        return True
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[CONNECTION_STATE] Connection/transaction is invalid: {e}")
        return False
