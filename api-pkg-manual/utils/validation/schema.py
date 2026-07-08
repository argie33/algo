#!/usr/bin/env python3
"""
Schema validation utilities for database tables.

Validates not just that tables/columns exist, but also that:
- Required columns are present (not empty)
- Column data types are correct
- Data type conversion won't fail

CRITICAL ISSUE #5 FIX: Validates column types, not just existence.
"""

import logging
from typing import Any

import psycopg2.sql

logger = logging.getLogger(__name__)


def validate_table_schema(
    cur: Any,
    table_name: str,
    required_columns: dict[str, str] | None = None,
    check_row_count: bool = True,
) -> tuple[bool, list[str]]:
    """Validate that a table exists and has correct column structure with proper data types.

    CRITICAL: This is a PRE-FLIGHT validation that catches schema mismatches BEFORE attempting
    to load data. It validates:
    1. Table exists
    2. All required columns exist
    3. All required columns have correct data types (not just existence)
    4. Optionally checks that table has data (for detection of schema issues)

    Args:
        cur: Database cursor
        table_name: Name of table to validate
        required_columns: Dict of {column_name: data_type} (e.g., {'price': 'numeric', 'symbol': 'varchar'})
        check_row_count: If True, also validates table has at least 1 row (default True). Set to False
                        for pre-flight validation before any data inserted.

    Returns:
        (is_valid, list of errors)
        - is_valid: True if all checks pass, False otherwise
        - errors: List of human-readable error messages explaining what failed

    Example:
        schema = {'symbol': 'varchar', 'date': 'date', 'close': 'numeric', 'volume': 'numeric'}
        is_valid, errors = validate_table_schema(cur, 'price_daily', schema, check_row_count=True)
        if not is_valid:
            for error in errors:
                logger.error(error)
            raise RuntimeError("Schema validation failed for price_daily")
    """
    errors = []

    if required_columns is None:
        required_columns = {}

    try:
        # Get actual column info from database
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY column_name
        """,
            (table_name,),
        )

        actual_columns = {row[0]: row[1] for row in cur.fetchall()}

        if not actual_columns:
            return False, [f"Table '{table_name}' does not exist"]

        # Check all required columns exist with correct types
        for col_name, expected_type in required_columns.items():
            if col_name not in actual_columns:
                errors.append(
                    f"Column '{col_name}' missing from table '{table_name}' "
                    f"(available columns: {', '.join(sorted(actual_columns.keys()))})"
                )
            else:
                actual_type = actual_columns[col_name]
                # Type validation (PostgreSQL type names)
                if not _types_compatible(actual_type, expected_type):
                    errors.append(
                        f"Column '{col_name}' in '{table_name}' has wrong type: "
                        f"expected '{expected_type}' but got '{actual_type}'. "
                        "This will cause runtime failures when loading data."
                    )

        # Optionally check table has data (useful for detecting schema-only issues)
        if check_row_count:
            from utils.db import assert_safe_table

            table_safe = assert_safe_table(table_name)
            cur.execute(psycopg2.sql.SQL("SELECT COUNT(*) FROM {} LIMIT 1").format(psycopg2.sql.Identifier(table_safe)))
            row = cur.fetchone()
            if row is None:
                raise RuntimeError(f"Schema validation for '{table_name}' failed: COUNT query returned no rows")
            row_count = row[0]
            if row_count == 0:
                errors.append(f"Table '{table_name}' is empty (0 rows)")

        return len(errors) == 0, errors

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Schema validation for '{table_name}' failed: {e}") from e


def _types_compatible(actual: str, expected: str) -> bool:
    """Check if actual PostgreSQL type is compatible with expected type.

    Handles both exact matches and compatible aliases:
    - numeric/decimal/float variants → numeric category
    - int2/int4/int8 → integer category
    - text/varchar/char → text category
    - date/timestamp/timestamptz → date category

    Args:
        actual: Actual PostgreSQL type name from information_schema (e.g., 'int4', 'text', 'numeric')
        expected: Expected type name from schema validation call (e.g., 'integer', 'text', 'numeric')

    Returns:
        True if types are compatible, False if they represent different data categories
    """
    # Map PostgreSQL type names to semantic categories
    # When the schema says 'numeric', we accept numeric/decimal/float variants
    # CRITICAL: This prevents TEXT from being accepted for numeric columns
    type_map = {
        # Integer types
        "int2": "integer",
        "int4": "integer",
        "int8": "integer",
        "serial": "integer",
        "bigserial": "integer",
        # Numeric/decimal types
        "numeric": "numeric",
        "decimal": "numeric",
        "float4": "numeric",
        "float8": "numeric",
        "real": "numeric",
        "double": "numeric",
        # Text types
        "text": "text",
        "varchar": "text",
        "char": "text",
        "character": "text",
        # Date/time types
        "date": "date",
        "timestamp": "date",
        "timestamptz": "date",
        "timestamp without time zone": "date",
        "timestamp with time zone": "date",
        "time": "date",
        "timetz": "date",
        # Boolean
        "boolean": "boolean",
        "bool": "boolean",
    }

    actual_type = type_map.get(actual.lower(), actual.lower())
    expected_type = type_map.get(expected.lower(), expected.lower())

    return actual_type == expected_type


def validate_row_data_types(row: dict[str, Any], table_name: str = "") -> list[str]:
    """Validate that row data can be converted to expected types.

    Args:
        row: Row data dict
        table_name: Table name (for error messages)

    Returns:
        List of validation errors (empty if all valid)
    """
    errors = []

    for col_name, value in row.items():
        if value is None:
            continue

        # Try basic conversions
        try:
            # Try to convert to float (most numeric columns)
            if isinstance(value, (int, float)):
                float(value)
            elif isinstance(value, str):
                # Check if it looks numeric
                if value and value[0] in "0123456789-.":
                    float(value)
        except (ValueError, TypeError) as e:
            errors.append(f"Column {col_name}: cannot convert {value!r} ({e})")

    return errors
