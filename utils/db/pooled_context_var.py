#!/usr/bin/env python3
"""Context variable tracking for pooled connections.

Allows loaders to acquire a connection once and reuse it for all database
operations without creating new DatabaseContext instances.

Works with OptimalLoader and PooledConnectionManager to reduce connection churn.
"""

import contextvars
from typing import Optional
import psycopg2

# Context variable holding the current thread's pooled connection
# Set by OptimalLoader at startup, used by DatabaseContext operations
_pooled_connection: contextvars.ContextVar[Optional[psycopg2.extensions.connection]] = contextvars.ContextVar(
    'pooled_connection',
    default=None
)


def set_pooled_connection(conn: Optional[psycopg2.extensions.connection]) -> None:
    """Set the current thread's pooled connection.

    Called by OptimalLoader.run() at startup.

    Args:
        conn: Connection to reuse for all database operations in this loader,
              or None to clear the pooled connection.
    """
    _pooled_connection.set(conn)


def get_pooled_connection() -> Optional[psycopg2.extensions.connection]:
    """Get the current thread's pooled connection (if set).

    Used by DatabaseContext to check for a reusable connection before
    acquiring a new one from the pool.

    Returns:
        Current pooled connection or None if not set
    """
    return _pooled_connection.get()


def has_pooled_connection() -> bool:
    """Check if a pooled connection is active in this thread."""
    return _pooled_connection.get() is not None
