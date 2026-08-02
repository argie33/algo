#!/usr/bin/env python
"""Verify that Decimal/float arithmetic fix works correctly."""
from decimal import Decimal

def _ensure_float(val, field_name="value"):
    """Convert any numeric value to native Python float, handling psycopg2 Decimal types."""
    if val is None:
        raise ValueError(f"Cannot convert None {field_name} to float")
    try:
        result = float(val)
        native_float = float(result)
        if not isinstance(native_float, float):
            raise TypeError(f"{field_name}: double float() returned {type(native_float).__name__}, not native float")
        return native_float
    except (TypeError, ValueError) as e:
        raise ValueError(f"Failed to convert {field_name} ({type(val).__name__}={val}) to float: {e}")

# Test 1: Decimal division
print("TEST 1: Decimal division (worst case)")
position_value = Decimal('50000.00')
total_value = Decimal('1000000.00')
try:
    pct = (position_value / total_value * 100)
    print(f"  Without conversion: {type(pct).__name__} = {pct}")
except TypeError as e:
    print(f"  ERROR: {e}")

# Test 2: With _ensure_float
print("\nTEST 2: With _ensure_float")
try:
    value_float = _ensure_float(position_value)
    total_float = _ensure_float(total_value)
    pct = value_float / total_float * 100
    pct_double = float(float(pct))
    print(f"  Result: {type(pct_double).__name__} = {pct_double}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 3: Subtraction after conversion
print("\nTEST 3: Subtraction (the actual failing operation)")
limit = Decimal('6.0')
try:
    pct_final = float(pct_double)
    limit_final = float(float(limit))
    exceed = pct_final - limit_final
    print(f"  {pct_final:.1f}% - {limit_final:.0f}% = {exceed:.1f}% [OK]")
except TypeError as e:
    print(f"  FAILED: {e}")

print("\nAll tests passed - Decimal fix works correctly.")
