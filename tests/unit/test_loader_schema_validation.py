#!/usr/bin/env python3
"""
Integration tests for loader schema validation.

Tests that loaders properly validate schema before attempting to load data.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestPriceLoaderSchemaValidation(unittest.TestCase):
    """Test PriceLoader schema validation integration."""

    @patch('utils.database_context.DatabaseContext')
    def test_schema_validation_passes_on_correct_schema(self, mock_db_context):
        """Schema validation should pass when table has correct column types."""
        # Mock database context
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),
            ('high', 'numeric'),
            ('low', 'numeric'),
            ('close', 'numeric'),
            ('volume', 'int8'),
            ('adj_close', 'numeric'),
        ]

        mock_db_context_instance = Mock()
        mock_db_context_instance.__enter__ = Mock(return_value=mock_cur)
        mock_db_context_instance.__exit__ = Mock(return_value=False)
        mock_db_context.return_value = mock_db_context_instance

        from loaders.load_prices import PriceLoader

        # Create loader
        loader = PriceLoader(interval='1d', asset_class='stock')

        # Validation should not raise
        try:
            loader._validate_schema_preflight()
        except RuntimeError:
            self.fail("Schema validation raised RuntimeError when schema was correct")

    @patch('utils.database_context.DatabaseContext')
    def test_schema_validation_fails_on_wrong_type(self, mock_db_context):
        """Schema validation should raise RuntimeError when column type is wrong."""
        # Mock database context with wrong column type
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),
            ('high', 'numeric'),
            ('low', 'numeric'),
            ('close', 'text'),  # ERROR: Should be numeric!
            ('volume', 'int8'),
            ('adj_close', 'numeric'),
        ]

        mock_db_context_instance = Mock()
        mock_db_context_instance.__enter__ = Mock(return_value=mock_cur)
        mock_db_context_instance.__exit__ = Mock(return_value=False)
        mock_db_context.return_value = mock_db_context_instance

        from loaders.load_prices import PriceLoader

        # Create loader
        loader = PriceLoader(interval='1d', asset_class='stock')

        # Validation should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            loader._validate_schema_preflight()

        self.assertIn('Schema validation failed', str(context.exception))
        self.assertIn('close', str(context.exception))
        self.assertIn('text', str(context.exception).lower())
        self.assertIn('numeric', str(context.exception).lower())

    @patch('utils.database_context.DatabaseContext')
    def test_schema_validation_fails_on_missing_column(self, mock_db_context):
        """Schema validation should raise RuntimeError when column is missing."""
        # Mock database context missing a column
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),
            ('high', 'numeric'),
            ('low', 'numeric'),
            # 'close' column is missing!
            ('volume', 'int8'),
        ]

        mock_db_context_instance = Mock()
        mock_db_context_instance.__enter__ = Mock(return_value=mock_cur)
        mock_db_context_instance.__exit__ = Mock(return_value=False)
        mock_db_context.return_value = mock_db_context_instance

        from loaders.load_prices import PriceLoader

        # Create loader
        loader = PriceLoader(interval='1d', asset_class='stock')

        # Validation should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            loader._validate_schema_preflight()

        self.assertIn('Schema validation failed', str(context.exception))
        self.assertIn('close', str(context.exception))

    @patch('utils.database_context.DatabaseContext')
    def test_schema_validation_handles_decimal_type(self, mock_db_context):
        """Schema validation should accept numeric for decimal columns."""
        # PostgreSQL uses 'numeric' for DECIMAL columns
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),  # PostgreSQL reports DECIMAL(12,4) as 'numeric'
            ('high', 'numeric'),
            ('low', 'numeric'),
            ('close', 'numeric'),
            ('volume', 'int8'),
            ('adj_close', 'numeric'),
        ]

        mock_db_context_instance = Mock()
        mock_db_context_instance.__enter__ = Mock(return_value=mock_cur)
        mock_db_context_instance.__exit__ = Mock(return_value=False)
        mock_db_context.return_value = mock_db_context_instance

        from loaders.load_prices import PriceLoader

        # Create loader
        loader = PriceLoader(interval='1d', asset_class='stock')

        # Should not raise
        try:
            loader._validate_schema_preflight()
        except RuntimeError:
            self.fail("Schema validation should accept 'numeric' for decimal columns")

    @patch('utils.database_context.DatabaseContext')
    def test_schema_validation_passes_for_etf_loader(self, mock_db_context):
        """Schema validation should work for ETF price loader."""
        mock_cur = Mock()
        mock_cur.fetchall.return_value = [
            ('symbol', 'varchar'),
            ('date', 'date'),
            ('open', 'numeric'),
            ('high', 'numeric'),
            ('low', 'numeric'),
            ('close', 'numeric'),
            ('volume', 'int8'),
        ]

        mock_db_context_instance = Mock()
        mock_db_context_instance.__enter__ = Mock(return_value=mock_cur)
        mock_db_context_instance.__exit__ = Mock(return_value=False)
        mock_db_context.return_value = mock_db_context_instance

        from loaders.load_prices import PriceLoader

        # Create ETF loader
        loader = PriceLoader(interval='1d', asset_class='etf')

        # Should not raise
        try:
            loader._validate_schema_preflight()
        except RuntimeError:
            self.fail("Schema validation should pass for ETF loader")


if __name__ == '__main__':
    unittest.main()
