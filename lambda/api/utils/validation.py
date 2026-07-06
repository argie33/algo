"""Validation utilities for database results and API responses."""

from __future__ import annotations

import json
from typing import Any


class DatabaseResultValidator:
    """Utility class for safely extracting typed values from database results."""

    @staticmethod
    def safe_get_str(
        data: dict[str, Any], key: str, default: str | None = None, strict: bool = False
    ) -> str | None:
        """Safely extract a string value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None
            strict: If True, raise exception on invalid data; if False, return default

        Returns:
            String value or default
        """
        if not isinstance(data, dict):
            if strict:
                raise ValueError(f"Expected dict, got {type(data).__name__}")
            return default
        value = data.get(key)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def safe_get_int(data: dict[str, Any], key: str, default: int | None = None) -> int | None:
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
    def safe_get_float(
        data: dict[str, Any], key: str, default: float | None = None, strict: bool = False
    ) -> float | None:
        """Safely extract a float value from a database result.

        Args:
            data: Dictionary of database result
            key: Key to extract
            default: Default value if key missing or value is None
            strict: If True, raise exception on invalid data; if False, return default

        Returns:
            Float value or default
        """
        if not isinstance(data, dict):
            if strict:
                raise ValueError(f"Expected dict, got {type(data).__name__}")
            return default
        value = data.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            if strict:
                raise ValueError(f"Cannot convert {key}={value} to float")
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

    @staticmethod
    def safe_get_first_row(data: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        """Safely extract the first row from a list of database results.

        Args:
            data: List of database results

        Returns:
            First row as dict or None if list is empty
        """
        if not isinstance(data, list) or len(data) == 0:
            return None
        return data[0]


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
        except ValueError as e:
            raise ValueError(f"Cannot convert string to float: {value}") from e

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
    "price_daily": {"max_age_hours": 24, "critical": True},
    "technical_data_daily": {"max_age_hours": 24, "critical": True},
    "market_exposure_daily": {"max_age_hours": 24, "critical": True},
    "stock_scores": {"max_age_hours": 24, "critical": True},
    "quality_metrics": {"max_age_hours": 168, "critical": False},
    "growth_metrics": {"max_age_hours": 168, "critical": True},
    "value_metrics": {"max_age_hours": 168, "critical": False},
    "positioning_metrics": {"max_age_hours": 168, "critical": False},
    "stability_metrics": {"max_age_hours": 168, "critical": False},
    "market_health_daily": {"max_age_hours": 24, "critical": True},
    "industry_ranking": {"max_age_hours": 168, "critical": False},
    "sector_ranking": {"max_age_hours": 24, "critical": True},
    "buy_sell_daily": {"max_age_hours": 24, "critical": True},
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


def assert_safe_column(column_name: str) -> str:
    """Verify column name is safe for SQL queries (alphanumeric + underscore only).

    Args:
        column_name: Column name to validate

    Returns:
        The column name if safe

    Raises:
        ValueError: If column name contains unsafe characters
    """
    if not isinstance(column_name, str):
        raise ValueError(f"Column name must be string, got {type(column_name).__name__}")

    # Only allow alphanumeric and underscore
    if not all(c.isalnum() or c == "_" for c in column_name):
        raise ValueError(f"Column name contains unsafe characters: {column_name}")

    return column_name
