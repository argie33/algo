"""Test decimal serialization fix for Issue #10."""
import json
from decimal import Decimal
import sys
from pathlib import Path

# Add lambda/api to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lambda' / 'api'))

from routes.utils import decimal_to_float_recursive


def test_decimal_to_float_recursive_scalar():
    """Test conversion of scalar Decimal values."""
    assert decimal_to_float_recursive(Decimal('10.25')) == 10.25
    assert isinstance(decimal_to_float_recursive(Decimal('10.25')), float)
    assert decimal_to_float_recursive(42) == 42
    assert decimal_to_float_recursive('string') == 'string'
    assert decimal_to_float_recursive(None) is None


def test_decimal_to_float_recursive_dict():
    """Test conversion of Decimal values in dictionaries."""
    input_dict = {
        'symbol': 'AAPL',
        'pct_change': Decimal('5.50'),
        'price': Decimal('150.25'),
        'nested': {
            'ratio': Decimal('0.75')
        }
    }
    result = decimal_to_float_recursive(input_dict)

    assert result['symbol'] == 'AAPL'
    assert result['pct_change'] == 5.50
    assert isinstance(result['pct_change'], float)
    assert result['price'] == 150.25
    assert result['nested']['ratio'] == 0.75


def test_decimal_to_float_recursive_list():
    """Test conversion of Decimal values in lists."""
    input_list = [
        {'value': Decimal('10.5')},
        {'value': Decimal('20.75')},
        {'value': Decimal('-5.25')}
    ]
    result = decimal_to_float_recursive(input_list)

    assert result[0]['value'] == 10.5
    assert result[1]['value'] == 20.75
    assert result[2]['value'] == -5.25
    assert all(isinstance(item['value'], float) for item in result)


def test_decimal_to_float_json_serializable():
    """Test that converted values can be serialized to JSON."""
    input_data = {
        'gainers': [
            {
                'symbol': 'AAPL',
                'security_name': 'Apple Inc',
                'pct_change': Decimal('5.50')
            }
        ],
        'losers': [
            {
                'symbol': 'MSFT',
                'security_name': 'Microsoft Corp',
                'pct_change': Decimal('-2.25')
            }
        ]
    }

    converted = decimal_to_float_recursive(input_data)

    # Should not raise TypeError
    json_str = json.dumps(converted)
    assert json_str is not None

    # Verify values are correct
    parsed = json.loads(json_str)
    assert parsed['gainers'][0]['pct_change'] == 5.50
    assert parsed['losers'][0]['pct_change'] == -2.25


def test_top_movers_decimal_handling():
    """Test the fix for /api/market/top-movers endpoint."""
    # Simulate what the endpoint does
    movers = [
        {
            'symbol': 'TSLA',
            'security_name': 'Tesla Inc',
            'pct_change': Decimal('8.75')
        },
        {
            'symbol': 'NIO',
            'security_name': 'NIO Inc',
            'pct_change': Decimal('-3.50')
        }
    ]

    # Apply the fix: convert with decimal_to_float_recursive
    items = [decimal_to_float_recursive(m) for m in movers]

    # Extract gainers and losers
    def get_pct_change(m):
        pc = m.get('pct_change')
        return pc if pc is not None else 0

    gainers = sorted([m for m in items if get_pct_change(m) >= 0],
                     key=lambda x: -get_pct_change(x))[:10]
    losers = sorted([m for m in items if get_pct_change(m) < 0],
                    key=lambda x: get_pct_change(x))[:10]

    response = {
        'gainers': gainers or [],
        'losers': losers or [],
        'items': items
    }

    # Verify it can be JSON serialized
    json_str = json.dumps(response)
    parsed = json.loads(json_str)

    assert parsed['gainers'][0]['pct_change'] == 8.75
    assert parsed['losers'][0]['pct_change'] == -3.50
    assert len(parsed['items']) == 2


if __name__ == '__main__':
    test_decimal_to_float_recursive_scalar()
    test_decimal_to_float_recursive_dict()
    test_decimal_to_float_recursive_list()
    test_decimal_to_float_json_serializable()
    test_top_movers_decimal_handling()
    print("All tests passed!")
