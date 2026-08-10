#!/usr/bin/env python3
"""Centralized error classification and handling for orchestrator phases.

Standardizes how errors are caught, categorized, logged, and reported across all phases.
Prevents inconsistent error handling that makes debugging and error recovery difficult.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Severity classification for phase errors."""

    TRANSIENT = "transient"  # Retry-able (network, timeout, lock contention)
    PERMANENT = "permanent"  # Not retry-able (data validation, logic, config)
    FATAL = "fatal"  # Halt entire run (data integrity, safety violation)


class PhaseErrorClassifier:
    """Classify exceptions into actionable error categories."""

    # Transient error types (safe to retry)
    TRANSIENT_ERROR_TYPES = (
        TimeoutError,
        ConnectionError,
        OSError,  # Includes socket errors
    )

    # Error messages that indicate transient conditions
    TRANSIENT_MESSAGE_PATTERNS = (
        "timeout",
        "connection",
        "connection closed",
        "pool exhausted",
        "lock",
        "deadlock",
        "timed out",
        "refused",
        "temporarily unavailable",
    )

    @staticmethod
    def classify(exc: Exception, error_message: str | None = None) -> ErrorSeverity:
        """Classify exception as transient, permanent, or fatal.

        Args:
            exc: The exception that occurred
            error_message: Optional error message for pattern matching

        Returns:
            ErrorSeverity classification
        """
        msg = error_message or str(exc)
        msg_lower = msg.lower()

        # Check for known transient error types
        if isinstance(exc, PhaseErrorClassifier.TRANSIENT_ERROR_TYPES):
            return ErrorSeverity.TRANSIENT

        # Check for transient message patterns
        for pattern in PhaseErrorClassifier.TRANSIENT_MESSAGE_PATTERNS:
            if pattern in msg_lower:
                return ErrorSeverity.TRANSIENT

        # Check for permanent error keywords
        if any(
            keyword in msg_lower
            for keyword in ("validation", "invalid", "missing required", "schema", "type error")
        ):
            return ErrorSeverity.PERMANENT

        # Check for fatal error keywords
        if any(keyword in msg_lower for keyword in ("critical", "halt", "integrity", "safety")):
            return ErrorSeverity.FATAL

        # Default: treat as permanent if unknown
        return ErrorSeverity.PERMANENT

    @staticmethod
    def log_error(
        phase_name: str,
        exc: Exception,
        context: dict[str, Any] | None = None,
        should_reraise: bool = False,
    ) -> ErrorSeverity:
        """Log an error with consistent format and classification.

        Args:
            phase_name: Name of phase where error occurred
            exc: The exception
            context: Optional context dict (symbol, position_id, etc.)
            should_reraise: If True, re-raise after logging

        Returns:
            ErrorSeverity classification

        Raises:
            The exception if should_reraise=True
        """
        severity = PhaseErrorClassifier.classify(exc)
        exc_type = type(exc).__name__
        context_str = f" | {context}" if context else ""

        log_msg = (
            f"[{phase_name}] {severity.value.upper()}: {exc_type}: {exc!s}{context_str}"
        )

        if severity == ErrorSeverity.FATAL:
            logger.error(log_msg)
        elif severity == ErrorSeverity.PERMANENT:
            logger.error(log_msg)
        else:
            logger.warning(log_msg)

        if should_reraise:
            raise exc

        return severity
