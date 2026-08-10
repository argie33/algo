"""Test NaN/Infinity JSON serialization fix.

Tests that NaN and Infinity values are properly converted to null during JSON serialization,
preventing "Unexpected token 'N'" JSON parse errors.
"""

import json
import math
import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Add lambda/api to path for imports
LAMBDA_API_PATH = Path(__file__).parent.parent.parent / "lambda" / "api"
if str(LAMBDA_API_PATH) not in sys.path:
    sys.path.insert(0, str(LAMBDA_API_PATH))


def test_safe_json_serialize_nan_values():
    """Test that safe_json_serialize converts NaN to None."""
    from routes.utils import safe_json_serialize

    # Test float NaN
    result = safe_json_serialize(float("nan"))
    assert result is None, f"Expected None for NaN, got {result}"

    # Test Decimal NaN
    decimal_nan = Decimal("NaN")
    result = safe_json_serialize(decimal_nan)
    assert result is None, f"Expected None for Decimal('NaN'), got {result}"

    # Test dict with NaN values
    data = {
        "valid": 1.5,
        "nan_float": float("nan"),
        "nan_decimal": Decimal("NaN"),
    }
    result = safe_json_serialize(data)
    assert result["valid"] == 1.5
    assert result["nan_float"] is None
    assert result["nan_decimal"] is None

    # Test list with NaN values
    data = [1.0, float("nan"), 3.0]
    result = safe_json_serialize(data)
    assert result == [1.0, None, 3.0]


def test_safe_json_serialize_infinity_values():
    """Test that safe_json_serialize converts Infinity to None."""
    from routes.utils import safe_json_serialize

    # Test positive infinity
    result = safe_json_serialize(float("inf"))
    assert result is None, f"Expected None for inf, got {result}"

    # Test negative infinity
    result = safe_json_serialize(float("-inf"))
    assert result is None, f"Expected None for -inf, got {result}"

    # Test Decimal infinity
    decimal_inf = Decimal("Infinity")
    result = safe_json_serialize(decimal_inf)
    assert result is None, f"Expected None for Decimal('Infinity'), got {result}"

    # Test dict with infinity values
    data = {
        "valid": 1.5,
        "pos_inf": float("inf"),
        "neg_inf": float("-inf"),
    }
    result = safe_json_serialize(data)
    assert result["valid"] == 1.5
    assert result["pos_inf"] is None
    assert result["neg_inf"] is None


def test_safe_json_serialize_valid_floats():
    """Test that valid floats are not affected by NaN/Infinity fix."""
    from routes.utils import safe_json_serialize

    data = {
        "zero": 0.0,
        "positive": 1.5,
        "negative": -2.3,
        "scientific": 1.23e-4,
        "large": 1e10,
    }
    result = safe_json_serialize(data)
    assert result == data


def test_safe_json_serialize_nested_structures():
    """Test NaN/Infinity handling in deeply nested structures."""
    from routes.utils import safe_json_serialize

    data = {
        "level1": {
            "level2": {
                "values": [1.0, float("nan"), {"inner_nan": float("nan"), "inner_inf": float("inf")}],
            }
        }
    }
    result = safe_json_serialize(data)

    # Verify structure
    assert result["level1"]["level2"]["values"][0] == 1.0
    assert result["level1"]["level2"]["values"][1] is None
    assert result["level1"]["level2"]["values"][2]["inner_nan"] is None
    assert result["level1"]["level2"]["values"][2]["inner_inf"] is None


def test_json_dumps_with_safe_json_serialize():
    """Test that safe_json_serialize output can be serialized with json.dumps."""
    from routes.utils import safe_json_serialize

    # This would fail without the fix
    data = {
        "symbol": "AAPL",
        "direction": float("nan"),
        "estimate": float("inf"),
        "price": 150.25,
    }

    # Serialize with safe_json_serialize
    safe_data = safe_json_serialize(data)

    # This should NOT raise "Unexpected token 'N'"
    json_str = json.dumps(safe_data)
    assert json_str is not None

    # Verify deserialization
    deserialized = json.loads(json_str)
    assert deserialized["symbol"] == "AAPL"
    assert deserialized["direction"] is None
    assert deserialized["estimate"] is None
    assert deserialized["price"] == 150.25


def test_list_response_with_nan_values():
    """Test that list_response handles NaN values properly."""
    from routes.utils import list_response, safe_json_serialize

    # Simulate data with NaN that might come from database
    items = [
        {"symbol": "AAPL", "direction": float("nan"), "price": 150.0},
        {"symbol": "MSFT", "direction": 1.0, "price": 300.0},
    ]

    # Serialize items with safe_json_serialize before list_response
    safe_items = [safe_json_serialize(item) for item in items]

    response = list_response(safe_items)

    # Verify response can be JSON-serialized
    json_str = json.dumps(response)
    assert json_str is not None

    # Verify data integrity
    deserialized = json.loads(json_str)
    assert deserialized["data"]["items"][0]["symbol"] == "AAPL"
    assert deserialized["data"]["items"][0]["direction"] is None
    assert deserialized["data"]["items"][1]["price"] == 300.0


def test_decimal_edge_cases():
    """Test Decimal edge cases (NaN, Infinity, Subnormal)."""
    from routes.utils import safe_json_serialize

    # Decimal NaN
    assert safe_json_serialize(Decimal("NaN")) is None

    # Decimal Infinity
    assert safe_json_serialize(Decimal("Infinity")) is None
    assert safe_json_serialize(Decimal("-Infinity")) is None

    # Decimal sNaN (signaling NaN)
    assert safe_json_serialize(Decimal("sNaN")) is None

    # Valid Decimal values should pass through as floats
    result = safe_json_serialize(Decimal("123.45"))
    assert isinstance(result, float)
    assert result == 123.45


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
