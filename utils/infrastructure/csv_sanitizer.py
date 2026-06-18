#!/usr/bin/env python3
"""
CSV/Excel Formula Injection Prevention

When exporting user-controlled data to CSV/Excel, special characters at the start
of a cell can trigger formula evaluation. For example, if a stock symbol starts with
'=', Excel will try to evaluate it as a formula.

This module provides sanitization functions to prevent formula injection attacks.

SECURITY: Always sanitize values before writing to CSV/Excel exports.
"""

import logging


logger = logging.getLogger(__name__)


def sanitize_for_csv(value) -> str:
    """
    Sanitize value for safe CSV/Excel export.

    Prevents formula injection by prefixing dangerous characters with a single quote.

    Args:
        value: Any value (string, number, etc.) to be exported

    Returns:
        Sanitized string safe for CSV/Excel export
    """
    if value is None:
        return ""

    str_val = str(value).strip()
    if not str_val:
        return ""

    # SECURITY: Prefix dangerous characters with single quote
    # This prevents Excel from evaluating them as formulas
    # Dangerous prefixes: =, +, -, @, tab, carriage return
    dangerous_prefixes = ("=", "+", "-", "@", "\t", "\r", "\n")

    if any(str_val.startswith(prefix) for prefix in dangerous_prefixes):
        logger.warning(
            f"Sanitizing CSV value that started with dangerous character: {str_val[:20]}"
        )
        return "'" + str_val

    return str_val


def sanitize_dict_for_csv(record: dict) -> dict:
    """
    Sanitize all values in a dictionary for CSV export.

    Args:
        record: Dictionary of values to export

    Returns:
        New dictionary with all values sanitized
    """
    return {key: sanitize_for_csv(value) for key, value in record.items()}


def sanitize_list_for_csv(records: list) -> list:
    """
    Sanitize all values in a list of dictionaries for CSV export.

    Args:
        records: List of dictionaries to export

    Returns:
        New list with all values sanitized
    """
    return [sanitize_dict_for_csv(record) for record in records]
