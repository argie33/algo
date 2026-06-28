#!/usr/bin/env python3
"""Schema Validator - Validate schema consistency across loaders."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates schema consistency before bulk inserts."""

    def __init__(self, expected_columns: list[str]) -> None:
        """Initialize with expected schema."""
        self.expected_columns = set(expected_columns)

    def validate_row_schema(self, row: dict[str, Any]) -> bool:
        """Validate that a row has all expected columns.

        Args:
            row: Row data to validate

        Returns:
            True if row schema is valid
        """
        row_columns = set(row.keys())
        if row_columns != self.expected_columns:
            missing = self.expected_columns - row_columns
            extra = row_columns - self.expected_columns
            if missing or extra:
                logger.warning(f"[SCHEMA] Mismatch: missing={missing}, extra={extra}")
            return False
        return True

    def validate_column_types(self, row: dict[str, Any], type_expectations: dict[str, type]) -> bool:
        """Validate that columns have expected types.

        Args:
            row: Row data to validate
            type_expectations: Map of column name to expected type

        Returns:
            True if all columns match expected types
        """
        for col, expected_type in type_expectations.items():
            if col not in row:
                continue
            if not isinstance(row[col], expected_type):
                logger.warning(f"[SCHEMA] {col}: expected {expected_type.__name__}, got {type(row[col]).__name__}")
                return False
        return True

    def validate_batch(self, rows: list[dict[str, Any]]) -> bool:
        """Validate entire batch for schema consistency.

        Args:
            rows: Batch of rows to validate

        Returns:
            True if all rows pass schema validation
        """
        for i, row in enumerate(rows):
            if not self.validate_row_schema(row):
                logger.error(f"[SCHEMA] Row {i} failed schema validation")
                return False
        logger.debug(f"[SCHEMA] Batch of {len(rows)} rows validated successfully")
        return True

    def get_expected_columns(self) -> set[str]:
        """Get expected columns."""
        return self.expected_columns.copy()
