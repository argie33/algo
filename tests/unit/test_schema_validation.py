#!/usr/bin/env python3
"""
Unit tests for pre-flight schema validation.

Tests that schema_validator correctly identifies schema mismatches
(column type changes) before data loading begins.
"""

import unittest
from unittest.mock import Mock, MagicMock
from utils.schema_validator import validate_table_schema, _types_compatible


class TestTypesCompatible(unittest.TestCase):
    """Test PostgreSQL type compatibility checking."""

    def test_numeric_variants_compatible(self):
        """Numeric column type variants should be considered compatible."""
        self.assertTrue(_types_compatible('numeric', 'numeric'))
        self.assertTrue(_types_compatible('decimal', 'numeric'))
        self.assertTrue(_types_compatible('float4', 'numeric'))
        self.assertTrue(_types_compatible('float8', 'numeric'))

    def test_integer_variants_compatible(self):
        """Integer column type variants should be considered compatible."""
        self.assertTrue(_types_compatible('int4', 'integer'))
        self.assertTrue(_types_compatible('int8', 'integer'))
        self.assertTrue(_types_compatible('bigserial', 'integer'))

    def test_text_variants_compatible(self):
        """Text column type variants should be considered compatible."""
        self.assertTrue(_types_compatible('text', 'text'))
        self.assertTrue(_types_compatible('varchar', 'text'))
        self.assertTrue(_types_compatible('character', 'text'))

    def test_date_variants_compatible(self):
        """Date/timestamp column type variants should be considered compatible."""
        self.assertTrue(_types_compatible('date', 'date'))
        self.assertTrue(_types_compatible('timestamp', 'date'))
        self.assertTrue(_types_compatible('timestamptz', 'date'))

    def test_incompatible_types_detected(self):
        """Incompatible types should be detected (e.g., TEXT for numeric column)."""
        self.assertFalse(_types_compatible('text', 'numeric'))
        self.assertFalse(_types_compatible('varchar', 'numeric'))
        self.assertFalse(_types_compatible('numeric', 'text'))
        self.assertFalse(_types_compatible('text', 'integer'))

    def test_case_insensitive(self):
        """Type comparison should be case-insensitive."""
        self.assertTrue(_types_compatible('TEXT', 'text'))
        self.assertTrue(_types_compatible('Numeric', 'NUMERIC'))
        self.assertTrue(_types_compatible('INT4', 'integer'))


class TestValidateTableSchema(unittest.TestCase):
    """Test validate_table_schema function."""

    def test_valid_schema(self):
        """Valid schema should return no errors."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('close', 'numeric'),
        ]

        is_valid, errors = validate_table_schema(
            mock_cur,
            'price_daily',
            required_columns={
                'symbol': 'varchar',
                'date': 'date',
                'close': 'numeric',
            },
            check_row_count=False
        )

        self.assertTrue(is_valid)
        self.assertEqual(errors, [])

    def test_missing_column(self):
        """Missing column should be reported as error."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
        ]

        is_valid, errors = validate_table_schema(
            mock_cur,
            'price_daily',
            required_columns={
                'symbol': 'varchar',
                'close': 'numeric',  # This column is missing
            },
            check_row_count=False
        )

        self.assertFalse(is_valid)
        self.assertTrue(any('close' in err for err in errors))

    def test_wrong_column_type(self):
        """Wrong column type should be reported as error."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('price', 'text'),  # Wrong type! Should be numeric
        ]

        is_valid, errors = validate_table_schema(
            mock_cur,
            'price_daily',
            required_columns={
                'symbol': 'varchar',
                'price': 'numeric',
            },
            check_row_count=False
        )

        self.assertFalse(is_valid)
        self.assertTrue(any('price' in err and 'wrong type' in err.lower() for err in errors))

    def test_table_not_found(self):
        """Non-existent table should be reported as error."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = []  # Empty result = table not found

        is_valid, errors = validate_table_schema(
            mock_cur,
            'nonexistent_table',
            required_columns={'col': 'text'},
            check_row_count=False
        )

        self.assertFalse(is_valid)
        self.assertTrue(any('does not exist' in err.lower() for err in errors))

    def test_decimal_type_accepted_for_numeric(self):
        """DECIMAL(12,4) should be compatible with numeric."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('price', 'numeric'),  # PostgreSQL udt_name for DECIMAL(12,4)
        ]

        is_valid, errors = validate_table_schema(
            mock_cur,
            'prices',
            required_columns={'price': 'numeric'},
            check_row_count=False
        )

        self.assertTrue(is_valid)
        self.assertEqual(errors, [])


class TestSchemaMisdetection(unittest.TestCase):
    """Test that schema mismatches are properly detected."""

    def test_price_column_as_text_detected(self):
        """Schema mismatch: price column as TEXT instead of NUMERIC should be caught."""
        mock_cur = Mock()
        # Simulate: price column somehow became TEXT (bad migration)
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),
            ('high', 'numeric'),
            ('low', 'numeric'),
            ('close', 'text'),  # ERROR: Should be numeric!
            ('volume', 'int8'),
        ]

        is_valid, errors = validate_table_schema(
            mock_cur,
            'price_daily',
            required_columns={
                'symbol': 'varchar',
                'date': 'date',
                'open': 'numeric',
                'high': 'numeric',
                'low': 'numeric',
                'close': 'numeric',
                'volume': 'integer',
            },
            check_row_count=False
        )

        # Validation should FAIL with clear error
        self.assertFalse(is_valid)
        self.assertTrue(any('close' in err and 'wrong type' in err.lower() for err in errors))
        self.assertTrue(any('text' in err.lower() and 'numeric' in err.lower() for err in errors))


if __name__ == '__main__':
    unittest.main()
