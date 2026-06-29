#!/usr/bin/env python3
"""
Centralized type conversion utilities for financial data processing.

Replaces duplicated safe_float/safe_int/safe_date patterns across 10+ loaders.
Provides consistent error handling and logging for type conversions.
"""

import logging
from datetime import date as date_type
from datetime import datetime

logger = logging.getLogger(__name__)


def safe_float(
    value: any,
    field_name: str = "value",
    default: float | None = None,
    strict: bool = False,
) -> float | None:
    """Convert value to float with consistent error handling.

    Args:
        value: Value to convert
        field_name: Field name for error logging
        default: Default value if conversion fails
        strict: If True, raise ValueError on None or conversion failure

    Returns:
        float or default value, or None if conversion fails and not strict
    """
    if value is None:
        if strict:
            raise ValueError(f"{field_name}: Cannot convert None to float in strict mode")
        return default

    if isinstance(value, float):
        return value

    if isinstance(value, int):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as e:
            if strict:
                raise ValueError(f"{field_name}: Cannot parse '{value}' as float") from e
            logger.debug(f"{field_name}: Skipping non-numeric value '{value}'")
            return default

    if strict:
        raise ValueError(f"{field_name}: Unsupported type {type(value).__name__}")

    logger.debug(f"{field_name}: Skipping unsupported type {type(value).__name__}")
    return default


def safe_int(
    value: any,
    field_name: str = "value",
    default: int | None = None,
    strict: bool = False,
) -> int | None:
    """Convert value to int with consistent error handling.

    Args:
        value: Value to convert
        field_name: Field name for error logging
        default: Default value if conversion fails
        strict: If True, raise ValueError on None or conversion failure

    Returns:
        int or default value, or None if conversion fails and not strict
    """
    if value is None:
        if strict:
            raise ValueError(f"{field_name}: Cannot convert None to int in strict mode")
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as e:
            if strict:
                raise ValueError(f"{field_name}: Cannot parse '{value}' as int") from e
            logger.debug(f"{field_name}: Skipping non-integer value '{value}'")
            return default

    if strict:
        raise ValueError(f"{field_name}: Unsupported type {type(value).__name__}")

    logger.debug(f"{field_name}: Skipping unsupported type {type(value).__name__}")
    return default


def safe_date(
    value: any,
    field_name: str = "value",
    default: date_type | None = None,
    strict: bool = False,
) -> date_type | None:
    """Convert value to date with consistent error handling.

    Args:
        value: Value to convert (date, datetime, or ISO format string)
        field_name: Field name for error logging
        default: Default value if conversion fails
        strict: If True, raise ValueError on None or conversion failure

    Returns:
        date or default value, or None if conversion fails and not strict
    """
    if value is None:
        if strict:
            raise ValueError(f"{field_name}: Cannot convert None to date in strict mode")
        return default

    if isinstance(value, date_type) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        try:
            # Try ISO format first (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            if "T" in value:
                return datetime.fromisoformat(value).date()
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError) as e:
            if strict:
                raise ValueError(f"{field_name}: Cannot parse '{value}' as date") from e
            logger.debug(f"{field_name}: Skipping invalid date format '{value}'")
            return default

    if strict:
        raise ValueError(f"{field_name}: Unsupported type {type(value).__name__}")

    logger.debug(f"{field_name}: Skipping unsupported type {type(value).__name__}")
    return default


def quarter_string_to_int(quarter_str: str, field_name: str = "fiscal_quarter") -> int | None:
    """Convert quarter string (Q1-Q4) to integer (1-4).

    Args:
        quarter_str: Quarter string like "Q1", "Q2", etc.
        field_name: Field name for error logging

    Returns:
        Integer 1-4, or None if invalid format
    """
    quarter_map = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}

    if not isinstance(quarter_str, str):
        logger.warning(f"{field_name}: Expected string, got {type(quarter_str).__name__}")
        return None

    quarter_num = quarter_map.get(quarter_str.upper().strip())
    if quarter_num is None:
        logger.warning(f"{field_name}: Invalid quarter format. Expected Q1-Q4, got '{quarter_str}'")
        return None

    return quarter_num
