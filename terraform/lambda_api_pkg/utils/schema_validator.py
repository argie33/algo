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
import psycopg2.sql
from typing import Dict, List, Optional, Tuple
from algo.algo_sql_safety import assert_safe_table

logger = logging.getLogger(__name__)


def validate_table_schema(cur, table_name: str, required_columns: Optional[Dict[str, str]] = None) -> Tuple[bool, List[str]]:
    """Validate that a table exists and has correct column structure.

    Args:
        cur: Database cursor
        table_name: Name of table to validate
        required_columns: Dict of {column_name: data_type}

    Returns:
        (is_valid, list of errors)
    """
    errors = []

    if required_columns is None:
        required_columns = {}

    try:
        # Get actual column info from database
        cur.execute("""
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY column_name
        """, (table_name,))

        actual_columns = {row[0]: row[1] for row in cur.fetchall()}

        if not actual_columns:
            return False, [f"Table {table_name} not found or is empty"]

        # Check all required columns exist
        for col_name, expected_type in required_columns.items():
            if col_name not in actual_columns:
                errors.append(f"Missing column: {col_name}")
            else:
                actual_type = actual_columns[col_name]
                # Basic type validation (PostgreSQL type names)
                if not _types_compatible(actual_type, expected_type):
                    errors.append(
                        f"Column {col_name} has wrong type: expected {expected_type}, got {actual_type}"
                    )

        # Check table has data
        table_safe = assert_safe_table(table_name)
        cur.execute(
            psycopg2.sql.SQL("SELECT COUNT(*) FROM {} LIMIT 1").format(
                psycopg2.sql.Identifier(table_safe)
            )
        )
        row_count = cur.fetchone()[0]
        if row_count == 0:
            errors.append(f"Table {table_name} is empty (0 rows)")

        return len(errors) == 0, errors

    except Exception as e:
        return False, [f"Schema validation failed: {e}"]


def _types_compatible(actual: str, expected: str) -> bool:
    """Check if actual PostgreSQL type is compatible with expected type.

    Args:
        actual: Actual PostgreSQL type name (e.g., 'int4', 'text', 'numeric')
        expected: Expected type (e.g., 'integer', 'text', 'numeric')

    Returns:
        True if types are compatible
    """
    # Map PostgreSQL type names to generic types
    type_map = {
        'int2': 'integer',
        'int4': 'integer',
        'int8': 'integer',
        'numeric': 'numeric',
        'float4': 'numeric',
        'float8': 'numeric',
        'text': 'text',
        'varchar': 'text',
        'char': 'text',
        'date': 'date',
        'timestamp': 'date',
        'timestamptz': 'date',
        'boolean': 'boolean',
    }

    actual_type = type_map.get(actual, actual)
    expected_type = type_map.get(expected, expected)

    return actual_type == expected_type


def validate_row_data_types(row: Dict, table_name: str = "") -> List[str]:
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
                if value and value[0] in '0123456789-.':
                    float(value)
        except (ValueError, TypeError) as e:
            errors.append(
                f"Column {col_name}: cannot convert {value!r} ({e})"
            )

    return errors
