"""Centralized type conversion utilities - eliminates 40+ duplicate float/int casting patterns."""

from decimal import Decimal
from typing import Any


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert value to float, handling None and common edge cases.

    Replaces 40+ duplicate patterns of: `float(x) if x is not None else None`

    Args:
        value: Value to convert (None, int, float, Decimal, str)
        default: Default value if conversion fails (default None)

    Returns:
        float, or default if conversion fails
    """
    if value is None:
        return default

    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            if value.is_nan():
                return default
            return float(value)
        if isinstance(value, str):
            if value.strip() == "":
                return default
            return float(value)
        return default
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Convert value to int, handling None and common edge cases.

    Args:
        value: Value to convert (None, int, float, str)
        default: Default value if conversion fails (default None)

    Returns:
        int, or default if conversion fails
    """
    if value is None:
        return default

    try:
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            if value.strip() == "":
                return default
            return int(value)
        return default
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """Convert value to string safely.

    Args:
        value: Value to convert
        default: Default value if None

    Returns:
        str representation, or default if None
    """
    if value is None:
        return default
    return str(value)


def safe_bool(value: Any, default: bool = False) -> bool:
    """Convert value to bool safely (handles strings like "yes", "1", etc).

    Args:
        value: Value to convert
        default: Default value if None

    Returns:
        bool representation
    """
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1", "on")

    # Numeric: 0 is False, anything else is True
    return bool(value)


def safe_decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    """Convert value to Decimal, handling None and NaN.

    Useful for financial data that needs precision.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Decimal, or default if conversion fails
    """
    if value is None:
        return default

    try:
        if isinstance(value, Decimal):
            if value.is_nan():
                return default
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))  # Use str to avoid float precision issues
        if isinstance(value, str):
            if value.strip() == "":
                return default
            return Decimal(value)
        return default
    except Exception:
        return default


def coerce_numeric_row(
    row: tuple[Any, ...],
    numeric_indices: list[int],
    float_indices: list[int] | None = None,
    int_indices: list[int] | None = None,
) -> tuple[Any, ...]:
    """Convert multiple fields in a row to float/int.

    Replaces 40+ duplicate patterns of manual field casting in loops.

    Args:
        row: Tuple of values from DB query
        numeric_indices: Indices to treat as floats by default
        float_indices: Specific indices to force to float (overrides numeric_indices)
        int_indices: Specific indices to force to int (overrides numeric_indices)

    Returns:
        Tuple with converted types
    """
    if float_indices is None:
        float_indices = []
    if int_indices is None:
        int_indices = []

    result = list(row)

    for idx in numeric_indices:
        if idx < len(result):
            if idx in int_indices:
                result[idx] = safe_int(result[idx])
            elif idx in float_indices:
                result[idx] = safe_float(result[idx])
            else:
                # Default to float for numeric fields
                result[idx] = safe_float(result[idx])

    return tuple(result)


class RowCaster:
    """Helper for casting specific columns in database rows.

    Usage:
        caster = RowCaster({"price": float, "quantity": int, "ratio": float})
        for row in results:
            clean_row = caster.cast(row)
    """

    def __init__(self, column_types: dict[str, type]):
        """Initialize with column name -> type mapping.

        Args:
            column_types: Dict mapping column names to types (float, int, str, bool)
        """
        self.column_types = column_types

    def cast_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Cast dictionary row by column specs.

        Args:
            row: Dictionary with column data

        Returns:
            Dictionary with cast values
        """
        result = dict(row)

        for col_name, col_type in self.column_types.items():
            if col_name not in result:
                continue

            if col_type is float:
                result[col_name] = safe_float(result[col_name])
            elif col_type is int:
                result[col_name] = safe_int(result[col_name])
            elif col_type is str:
                result[col_name] = safe_str(result[col_name])
            elif col_type is bool:
                result[col_name] = safe_bool(result[col_name])
            elif col_type is Decimal:
                result[col_name] = safe_decimal(result[col_name])

        return result

    def cast_tuple(self, row: tuple[Any, ...], columns: list[str]) -> tuple[Any, ...]:
        """Cast tuple row by column specs.

        Args:
            row: Tuple with row data
            columns: List of column names (parallel to row tuple)

        Returns:
            Tuple with cast values
        """
        if len(row) != len(columns):
            raise ValueError(f"Row length {len(row)} != column count {len(columns)}")

        result = list(row)

        for idx, col_name in enumerate(columns):
            if col_name in self.column_types:
                col_type = self.column_types[col_name]

                if col_type is float:
                    result[idx] = safe_float(result[idx])
                elif col_type is int:
                    result[idx] = safe_int(result[idx])
                elif col_type is str:
                    result[idx] = safe_str(result[idx])
                elif col_type is bool:
                    result[idx] = safe_bool(result[idx])
                elif col_type is Decimal:
                    result[idx] = safe_decimal(result[idx])

        return tuple(result)
