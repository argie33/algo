#!/usr/bin/env python3
"""Enum validation for loader state fields.

ISSUE #12 FIX: Validate that all state fields have valid enum values before
inserting to database. Prevents invalid state from persisting.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Valid enum values for loader state fields
VALID_STATUSES = {"RUNNING", "COMPLETED", "FAILED", "SKIPPED", "PARTIAL"}
VALID_PERIODS = {"annual", "quarterly", "ttm"}
VALID_STATEMENT_TYPES = {"income", "balance", "cashflow"}
VALID_INTERVALS = {"1d", "1wk", "1mo"}


def validate_status(status: str, context: str = "") -> None:
    """Validate loader status field.

    Args:
        status: Status value to validate
        context: Context for error message (e.g., 'price_loader')

    Raises:
        ValueError: If status is invalid
    """
    if status not in VALID_STATUSES:
        msg = (
            f"ENUM VALIDATION FAILED: Invalid status '{status}' {context}. "
            f"Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
        logger.error(msg)
        raise ValueError(msg)


def validate_period(period: str, context: str = "") -> None:
    """Validate financial statement period field.

    Args:
        period: Period value to validate
        context: Context for error message

    Raises:
        ValueError: If period is invalid
    """
    if period not in VALID_PERIODS:
        msg = (
            f"ENUM VALIDATION FAILED: Invalid period '{period}' {context}. "
            f"Must be one of: {', '.join(sorted(VALID_PERIODS))}"
        )
        logger.error(msg)
        raise ValueError(msg)


def validate_statement_type(statement_type: str, context: str = "") -> None:
    """Validate financial statement type field.

    Args:
        statement_type: Statement type value to validate
        context: Context for error message

    Raises:
        ValueError: If statement_type is invalid
    """
    if statement_type not in VALID_STATEMENT_TYPES:
        msg = (
            f"ENUM VALIDATION FAILED: Invalid statement_type '{statement_type}' {context}. "
            f"Must be one of: {', '.join(sorted(VALID_STATEMENT_TYPES))}"
        )
        logger.error(msg)
        raise ValueError(msg)


def validate_interval(interval: str, context: str = "") -> None:
    """Validate price interval field.

    Args:
        interval: Interval value to validate
        context: Context for error message

    Raises:
        ValueError: If interval is invalid
    """
    if interval not in VALID_INTERVALS:
        msg = (
            f"ENUM VALIDATION FAILED: Invalid interval '{interval}' {context}. "
            f"Must be one of: {', '.join(sorted(VALID_INTERVALS))}"
        )
        logger.error(msg)
        raise ValueError(msg)


def validate_row_enums(row: dict[str, Any], required_enums: dict[str, set[str]], context: str = "") -> None:
    """Validate multiple enum fields in a data row.

    Args:
        row: Data row to validate
        required_enums: Dict mapping field names to valid enum values
        context: Context for error messages

    Raises:
        ValueError: If any enum field is invalid
    """
    for field_name, valid_values in required_enums.items():
        value = row.get(field_name)
        if value is not None and value not in valid_values:
            msg = (
                f"ENUM VALIDATION FAILED: Row {context} has invalid '{field_name}': '{value}'. "
                f"Must be one of: {', '.join(sorted(valid_values))}"
            )
            logger.error(msg)
            raise ValueError(msg)
