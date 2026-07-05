"""Validation utilities for database results and API responses."""

from __future__ import annotations

import json
from typing import Any


class DatabaseResultValidator:
    """Utility class for safely extracting typed values from database results."""

    @staticmethod
    def safe_get_str(data: dict[str, Any], key: str, default: str = "") -> str:
        """Safely extract a string value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None

        Returns:
            String value or default
        """
        if not isinstance(data, dict):
            return default
        value = data.get(key)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def safe_get_int(data: dict[str, Any], key: str, default: int = 0) -> int:
        """Safely extract an int value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None

        Returns:
            Int value or default
        """
        if not isinstance(data, dict):
            return default
        value = data.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def safe_get_float(data: dict[str, Any], key: str, default: float = 0.0) -> float:
        """Safely extract a float value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None

        Returns:
            Float value or default
        """
        if not isinstance(data, dict):
            return default
        value = data.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def safe_get_bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
        """Safely extract a bool value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None

        Returns:
            Bool value or default
        """
        if not isinstance(data, dict):
            return default
        value = data.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)


class APIResponseValidator:
    """Validates and sanitizes API response data."""

    @staticmethod
    def sanitize_response(data: Any) -> Any:
        """Sanitize response data to ensure it's JSON-serializable.

        Args:
            data: Response data to sanitize

        Returns:
            Sanitized data that can be JSON-serialized
        """
        if data is None:
            return None

        if isinstance(data, (str, int, float, bool)):
            return data

        if isinstance(data, dict):
            # Sanitize dict values
            return {k: APIResponseValidator.sanitize_response(v) for k, v in data.items()}

        if isinstance(data, (list, tuple)):
            # Sanitize list items
            return [APIResponseValidator.sanitize_response(item) for item in data]

        # Try to JSON-serialize to check if it's serializable
        try:
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            # If not serializable, convert to string
            return str(data)


def get_optional_field(data: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    """Safely extract an optional field from a dictionary.

    Args:
        data: Dictionary to extract from
        key: Key to extract
        default: Default value if key missing or value is None

    Returns:
        Field value or default
    """
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def get_required_field(data: dict[str, Any], key: str) -> Any:
    """Safely extract a required field from a dictionary.

    Args:
        data: Dictionary to extract from
        key: Key to extract

    Returns:
        Field value

    Raises:
        KeyError: If key missing
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data).__name__}")
    if key not in data:
        raise KeyError(f"Required field missing: {key}")
    return data[key]


def format_decimal_string(value: Any, precision: int = 2, allow_none: bool = True) -> str | None:
    """Format a numeric value as a string with specified decimal places.

    Args:
        value: Value to format (int, float, Decimal, or string)
        precision: Number of decimal places (default 2)
        allow_none: If True, return None for None input; if False, raise error

    Returns:
        Formatted string or None
    """
    if value is None:
        if allow_none:
            return None
        raise ValueError("Value is None but allow_none=False")

    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ValueError(f"Cannot convert string to float: {value}")

    try:
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError) as e:
        raise ValueError(f"Cannot format value as decimal: {value}") from e


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Safely convert a value to float.

    Args:
        value: Value to convert
        default: Default value if conversion fails or value is None

    Returns:
        Float value or default
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# Data freshness rules for different table types
# Maps table_name to max_age_hours before data is considered stale
FRESHNESS_RULES = {
    "price_daily": 24,
    "technical_data_daily": 24,
    "market_exposure_daily": 24,
    "stock_scores": 24,
    "quality_metrics": 168,  # 7 days
    "growth_metrics": 168,  # 7 days
    "value_metrics": 168,  # 7 days
    "positioning_metrics": 168,  # 7 days
    "stability_metrics": 168,  # 7 days
    "market_health_daily": 24,
    "industry_ranking": 168,  # 7 days
    "sector_ranking": 24,
    "buy_sell_daily": 24,
}


def assert_safe_table(table_name: str) -> str:
    """Verify table name is safe for SQL queries (alphanumeric + underscore only).

    Args:
        table_name: Table name to validate

    Returns:
        The table name if safe

    Raises:
        ValueError: If table name contains unsafe characters
    """
    if not isinstance(table_name, str):
        raise ValueError(f"Table name must be string, got {type(table_name).__name__}")

    # Only allow alphanumeric and underscore
    if not all(c.isalnum() or c == "_" for c in table_name):
        raise ValueError(f"Table name contains unsafe characters: {table_name}")

    return table_name
