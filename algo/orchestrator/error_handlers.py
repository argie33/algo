#!/usr/bin/env python3
"""
Common error handling utilities for orchestrator phases.

Consolidates repeated error handling patterns across Phase 1-9 to reduce code duplication
and ensure consistent error logging, database recovery, and phase result handling.
"""

import logging
from collections.abc import Callable
from typing import TypeVar

import psycopg2

logger = logging.getLogger(__name__)

T = TypeVar("T")


def handle_database_error(
    phase_num: int,
    error: Exception,
    context: str = "",
    log_critical: bool = True,
) -> tuple[bool, str]:
    """Handle database errors with consistent logging and classification.

    Args:
        phase_num: Phase number for logging
        error: The exception that occurred
        context: Additional context string for logs
        log_critical: Whether to log as CRITICAL (True) or ERROR (False)

    Returns:
        Tuple of (is_transient, error_message) where:
        - is_transient: True if error might resolve on retry (connection, timeout, deadlock)
        - error_message: Formatted error message for logging/reporting
    """
    error_type = type(error).__name__
    error_msg = str(error)

    # Classify errors by transience
    transient_keywords = ("timeout", "connection", "pool", "concurrent", "deadlock", "FATAL", "try again")
    is_transient = any(kw.lower() in error_msg.lower() for kw in transient_keywords)

    full_msg = f"[PHASE {phase_num}] {error_type}: {error_msg}"
    if context:
        full_msg = f"{context} - {full_msg}"

    if log_critical and not is_transient:
        logger.critical(full_msg)
    else:
        logger.error(full_msg)

    return is_transient, full_msg


def handle_generic_error(
    phase_num: int,
    error: Exception,
    context: str = "",
    halting: bool = False,
) -> str:
    """Handle generic (non-database) errors with consistent logging.

    Args:
        phase_num: Phase number for logging
        error: The exception that occurred
        context: Additional context string
        halting: If True, log as CRITICAL; if False, as ERROR

    Returns:
        Formatted error message
    """
    error_type = type(error).__name__
    error_msg = str(error)
    full_msg = f"[PHASE {phase_num}] {error_type}: {error_msg}"
    if context:
        full_msg = f"{context} - {full_msg}"

    if halting:
        logger.critical(full_msg)
    else:
        logger.error(full_msg)

    return full_msg


def wrap_db_operation(
    phase_num: int,
    operation_name: str,
    operation_fn: Callable[[], T],
    on_transient_error: Callable[[str], None] | None = None,
    on_fatal_error: Callable[[str], None] | None = None,
    max_retries: int = 0,
) -> T | None:
    """Wrap a database operation with automatic error handling and optional retry.

    Args:
        phase_num: Phase number for logging
        operation_name: Human-readable name of operation (for logging)
        operation_fn: Function that performs the DB operation
        on_transient_error: Optional callback on transient errors (connection issues, etc)
        on_fatal_error: Optional callback on fatal errors
        max_retries: Number of retries for transient errors (0 = no retry)

    Returns:
        Result of operation_fn if successful, None if fatal error
    """
    attempt = 0

    while attempt <= max_retries:
        try:
            return operation_fn()
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            is_transient, error_msg = handle_database_error(phase_num, e, context=operation_name)

            if is_transient and attempt < max_retries:
                attempt += 1
                if on_transient_error:
                    on_transient_error(error_msg)
                continue

            if on_fatal_error:
                on_fatal_error(error_msg)
            return None

        except Exception as e:
            error_msg = handle_generic_error(phase_num, e, context=operation_name, halting=True)
            if on_fatal_error:
                on_fatal_error(error_msg)
            return None

    return None
