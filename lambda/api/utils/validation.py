"""Validation utilities for database results."""

from __future__ import annotations

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
