#!/usr/bin/env python3
"""Standardized loader status enum - single source of truth for all status values.

CRITICAL: All loaders MUST use these status strings. No arbitrary status values allowed.

Usage:
    from utils.loaders.status_enum import LoaderStatus

    # ✓ Correct
    cur.execute("UPDATE data_loader_status SET status = %s", (LoaderStatus.RUNNING,))

    # ✗ Wrong - will type error
    cur.execute("UPDATE data_loader_status SET status = 'running'")  # string not allowed
"""

from enum import Enum


class LoaderStatus(str, Enum):
    """Valid status values for data_loader_status table.

    Naming: ALL CAPS to match existing database values (e.g., 'RUNNING', 'COMPLETED')

    State machine:
        NOT_STARTED → RUNNING → COMPLETED (success)
                   → FAILED (error)
                   → TIMEOUT (exceeded max_runtime)

    Additionally: IDLE = loader never registered/configured, READY = loaded before but not running now
    """

    # Loader hasn't started yet (status row exists but execution_started is NULL)
    NOT_STARTED = "NOT_STARTED"

    # Loader is actively running (execution_started set, not yet completed)
    RUNNING = "RUNNING"

    # Loader completed successfully (execution_completed set, no errors)
    COMPLETED = "COMPLETED"

    # Loader encountered an error and stopped (error_message populated)
    FAILED = "FAILED"

    # Loader exceeded timeout threshold
    TIMEOUT = "TIMEOUT"

    # Loader never executed (only for historical backward compatibility - don't use for new loaders)
    # These should transition to NOT_STARTED immediately
    IDLE = "IDLE"
    READY = "READY"

    # No data available for this loader (might not apply to all symbols/dates)
    EMPTY = "EMPTY"

    # Unclear/legacy - should be deprecated
    OK = "OK"

    def __str__(self) -> str:
        """Return string value for database operations."""
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "LoaderStatus":
        """Convert string to enum, with validation.

        Raises ValueError if string is not a valid status.
        This prevents typos like 'completed' (lowercase) which won't match database queries.
        """
        try:
            return cls(value)
        except ValueError as e:
            valid_values = [s.value for s in cls]
            raise ValueError(
                f"[LOADER STATUS] Invalid status '{value}'. "
                f"Must be one of: {', '.join(valid_values)}"
            ) from e

    @classmethod
    def all_strings(cls) -> list[str]:
        """Return all valid status strings for use in SQL IN clauses."""
        return [s.value for s in cls]

    @classmethod
    def is_running(cls, status: str) -> bool:
        """Check if loader is currently executing."""
        return status in (cls.RUNNING.value, cls.NOT_STARTED.value)

    @classmethod
    def is_complete(cls, status: str) -> bool:
        """Check if loader execution finished (success or failure)."""
        return status in (cls.COMPLETED.value, cls.FAILED.value, cls.TIMEOUT.value)

    @classmethod
    def is_error(cls, status: str) -> bool:
        """Check if loader encountered an error."""
        return status in (cls.FAILED.value, cls.TIMEOUT.value)
