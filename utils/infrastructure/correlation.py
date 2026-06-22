#!/usr/bin/env python3
"""
Correlation ID Context Manager

Provides thread-safe storage and retrieval of correlation_id for end-to-end
tracing across database operations, logs, and function calls.

Usage:
    # At loader startup:
    set_correlation_id("abc123")

    # In any function, get current correlation_id:
    cid = get_correlation_id()

    # Or use context manager to set temporarily:
    with correlation_context("xyz789"):
        # All code in this block sees correlation_id = "xyz789"
        logger.info("Processing", extra={"correlation_id": get_correlation_id()})
"""

import contextvars
import uuid
from contextlib import contextmanager

# Thread-safe context variable for correlation_id
_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("correlation_id", default=None)


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for this execution context.

    Typically called once at the start of a loader run.
    All subsequent database operations and logs will include this ID.

    Args:
        correlation_id: Unique ID to trace this execution
    """
    _correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """Get the current correlation ID, or generate a new one if not set.

    Returns:
        Current correlation_id or a freshly generated one
    """
    cid = _correlation_id_var.get()
    if cid is None:
        cid = f"GEN-{str(uuid.uuid4())[:8]}"
        _correlation_id_var.set(cid)
    return cid


@contextmanager
def correlation_context(correlation_id: str):
    """Context manager to temporarily set correlation_id.

    Usage:
        with correlation_context("temp-id-123"):
            # All code here sees get_correlation_id() == "temp-id-123"
            logger.info("Message")

    Args:
        correlation_id: Temporary ID to use in this context

    Yields:
        The correlation_id that was set
    """
    token = _correlation_id_var.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _correlation_id_var.reset(token)


def reset_correlation_id() -> None:
    """Clear the correlation ID (for testing or manual cleanup)."""
    _correlation_id_var.set(None)
