#!/usr/bin/env python3
"""Database query result validation helpers.

Provides safe helpers for accessing tuple-based query results with validation.
Prevents IndexError and makes code more readable by replacing magic indices
with named field access.
"""

from typing import Any, TypeVar, cast

T = TypeVar("T")


class RowValidationError(Exception):
    """Raised when query result row structure is unexpected."""


def validate_row_structure(
    row: tuple[Any, ...] | list[Any],
    expected_columns: list[str],
    source: str = "query",
) -> None:
    """Validate that a row has the expected number and type of columns.

    Args:
        row: Row from database query (tuple or list)
        expected_columns: List of column names (used only for error messages)
        source: Description of query source (for error messages)

    Raises:
        RowValidationError: If row structure doesn't match expectations
    """
    if not isinstance(row, (tuple, list)):
        raise RowValidationError(
            f"[{source}] Expected row to be tuple or list, got {type(row).__name__}"
        )

    expected_count = len(expected_columns)
    actual_count = len(row)

    if actual_count != expected_count:
        raise RowValidationError(
            f"[{source}] Row has {actual_count} columns, expected {expected_count}. "
            f"Expected columns: {expected_columns}. "
            f"Actual row has {actual_count} values: {row}. "
            f"This indicates a query structure mismatch or schema drift."
        )


def safe_get_column(
    row: tuple[Any, ...] | list[Any],
    index: int,
    column_name: str,
    expected_type: type | tuple[type, ...] | None = None,
    source: str = "query",
    allow_none: bool = False,
) -> Any:
    """Safely access a column from a query result row with validation.

    Args:
        row: Row from database query
        index: Zero-indexed column position
        column_name: Human-readable column name (for error messages)
        expected_type: Expected type(s) of value, or None to skip type check
        source: Description of query source (for error messages)
        allow_none: If True, None values are allowed; if False, None raises error

    Returns:
        Value at the specified index

    Raises:
        RowValidationError: If value is missing, wrong type, or None when not allowed
    """
    if not isinstance(row, (tuple, list)):
        raise RowValidationError(
            f"[{source}] {column_name}: Row is {type(row).__name__}, expected tuple or list"
        )

    if index >= len(row):
        raise RowValidationError(
            f"[{source}] {column_name}: Column index {index} out of bounds. "
            f"Row has {len(row)} columns."
        )

    value = row[index]

    if value is None:
        if not allow_none:
            raise RowValidationError(
                f"[{source}] {column_name}: Column value is NULL, but NULL is not allowed"
            )
        return None

    if expected_type is not None:
        if not isinstance(value, expected_type):
            actual_type = type(value).__name__
            if isinstance(expected_type, tuple):
                expected_str = " or ".join(t.__name__ for t in expected_type)
            else:
                expected_str = expected_type.__name__
            raise RowValidationError(
                f"[{source}] {column_name}: Column has type {actual_type}, expected {expected_str}"
            )

    return value


class RowAccessor:
    """Type-safe accessor for tuple-based query results.

    Usage:
        accessor = RowAccessor(row, ['symbol', 'price', 'quantity'])
        symbol = accessor.get_str(0)
        price = accessor.get_float(1, allow_none=True)
        quantity = accessor.get_int(2)
    """

    def __init__(
        self,
        row: tuple[Any, ...] | list[Any],
        column_names: list[str],
        source: str = "query",
    ):
        """Initialize accessor with row and expected column structure.

        Args:
            row: Row from database query
            column_names: List of column names (used for error messages)
            source: Description of query source (for error messages)
        """
        validate_row_structure(row, column_names, source)
        self.row = row
        self.column_names = column_names
        self.source = source

    def get(
        self,
        index: int,
        expected_type: type | tuple[type, ...] | None = None,
        allow_none: bool = False,
    ) -> Any:
        """Get column value with type checking."""
        column_name = (
            self.column_names[index]
            if 0 <= index < len(self.column_names)
            else f"column_{index}"
        )
        return safe_get_column(
            self.row,
            index,
            column_name,
            expected_type,
            self.source,
            allow_none,
        )

    def get_str(self, index: int, allow_none: bool = False) -> str | None:
        """Get string column."""
        return cast(str | None, self.get(index, str, allow_none))

    def get_int(self, index: int, allow_none: bool = False) -> int | None:
        """Get integer column."""
        return cast(int | None, self.get(index, int, allow_none))

    def get_float(self, index: int, allow_none: bool = False) -> float | None:
        """Get float column (int, float, and Decimal accepted; Decimal is converted to float).

        CRITICAL FIX: psycopg2 returns NUMERIC/DECIMAL columns (prices, quantities, most
        money-shaped columns in this schema) as decimal.Decimal, never native float. This
        method's accepted-type tuple was (int, float) - it never accepted Decimal at all,
        so ANY real query row containing an actual Decimal value raised
        RowValidationError("Column has type Decimal, expected int or float") despite the
        docstring's stated purpose of being the safe way to read a float column. Live-caught
        2026-08-03: phase3_position_monitor.py's own price_daily.close read via this method
        failed on every real position - invisible all session because there were zero real
        open positions to exercise the path until a synthetic end-to-end verification test.
        """
        from decimal import Decimal

        value = self.get(index, (int, float, Decimal), allow_none)
        return float(value) if value is not None else None

    def get_bool(self, index: int, allow_none: bool = False) -> bool | None:
        """Get boolean column."""
        return cast(bool | None, self.get(index, bool, allow_none))
