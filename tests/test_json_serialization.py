"""Tests for JSON serialization safety across all API routes."""
import pytest
from decimal import Decimal
from datetime import datetime, date
from uuid import UUID
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambda', 'api', 'routes'))

from utils import safe_json_serialize


class TestSafeJsonSerialize:
    """Test safe_json_serialize handles all non-JSON-serializable types."""

    def test_decimal_conversion(self):
        """Decimal should convert to float."""
        assert safe_json_serialize(Decimal('10.5')) == 10.5
        assert safe_json_serialize(Decimal('0')) == 0.0
        assert safe_json_serialize(Decimal('-5.25')) == -5.25

    def test_datetime_conversion(self):
        """datetime should convert to ISO string."""
        dt = datetime(2026, 6, 11, 14, 30, 45)
        result = safe_json_serialize(dt)
        assert result == '2026-06-11T14:30:45'
        assert isinstance(result, str)

    def test_date_conversion(self):
        """date should convert to ISO string."""
        d = date(2026, 6, 11)
        result = safe_json_serialize(d)
        assert result == '2026-06-11'
        assert isinstance(result, str)

    def test_uuid_conversion(self):
        """UUID should convert to string."""
        u = UUID('550e8400-e29b-41d4-a716-446655440000')
        result = safe_json_serialize(u)
        assert result == '550e8400-e29b-41d4-a716-446655440000'
        assert isinstance(result, str)

    def test_dict_with_decimal(self):
        """Dict with Decimal values should be fully converted."""
        data = {
            'price': Decimal('99.99'),
            'quantity': Decimal('10'),
            'nested': {'value': Decimal('5.5')}
        }
        result = safe_json_serialize(data)
        assert result == {
            'price': 99.99,
            'quantity': 10.0,
            'nested': {'value': 5.5}
        }

    def test_dict_with_datetime(self):
        """Dict with datetime values should be fully converted."""
        dt = datetime(2026, 6, 11, 15, 45, 0)
        data = {
            'created_at': dt,
            'metadata': {'updated_at': dt}
        }
        result = safe_json_serialize(data)
        assert result == {
            'created_at': '2026-06-11T15:45:00',
            'metadata': {'updated_at': '2026-06-11T15:45:00'}
        }

    def test_list_with_mixed_types(self):
        """List with mixed types should be fully converted."""
        data = [
            Decimal('10.5'),
            datetime(2026, 6, 11),
            {'price': Decimal('99.99'), 'date': date(2026, 6, 11)},
            UUID('550e8400-e29b-41d4-a716-446655440000')
        ]
        result = safe_json_serialize(data)
        assert result == [
            10.5,
            '2026-06-11T00:00:00',
            {'price': 99.99, 'date': '2026-06-11'},
            '550e8400-e29b-41d4-a716-446655440000'
        ]

    def test_complex_nested_structure(self):
        """Complex nested structure with all types should convert correctly."""
        data = {
            'trades': [
                {
                    'id': UUID('550e8400-e29b-41d4-a716-446655440000'),
                    'entry_price': Decimal('100.50'),
                    'entry_date': date(2026, 6, 10),
                    'entry_time': datetime(2026, 6, 10, 9, 30, 0),
                    'metadata': {
                        'profit_loss': Decimal('-5.25'),
                        'timestamp': datetime(2026, 6, 11, 15, 45, 0)
                    }
                }
            ]
        }
        result = safe_json_serialize(data)
        assert result == {
            'trades': [
                {
                    'id': '550e8400-e29b-41d4-a716-446655440000',
                    'entry_price': 100.50,
                    'entry_date': '2026-06-10',
                    'entry_time': '2026-06-10T09:30:00',
                    'metadata': {
                        'profit_loss': -5.25,
                        'timestamp': '2026-06-11T15:45:00'
                    }
                }
            ]
        }

    def test_null_values_preserved(self):
        """None/null values should be preserved."""
        data = {
            'value': None,
            'list': [None, Decimal('10'), None],
            'nested': {'inner': None}
        }
        result = safe_json_serialize(data)
        assert result == {
            'value': None,
            'list': [None, 10.0, None],
            'nested': {'inner': None}
        }

    def test_passthrough_types(self):
        """Regular JSON-serializable types should pass through unchanged."""
        data = {
            'string': 'hello',
            'number': 42,
            'float': 3.14,
            'bool': True,
            'null': None,
            'list': [1, 2, 'three'],
            'nested_dict': {'key': 'value'}
        }
        result = safe_json_serialize(data)
        assert result == data

    def test_empty_collections(self):
        """Empty collections should remain empty."""
        data = {'empty_list': [], 'empty_dict': {}}
        result = safe_json_serialize(data)
        assert result == data

    def test_import_available(self):
        """Verify safe_json_serialize is exported from utils."""
        from utils import safe_json_serialize as sjs
        assert callable(sjs)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
