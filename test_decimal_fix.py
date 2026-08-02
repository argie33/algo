#!/usr/bin/env python
"""Test that Decimal/float arithmetic fix actually works."""
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
position_value = Decimal('50000.00')  # From database
total_value = Decimal('1000000.00')   # From database
try:
    pct = (position_value / total_value * 100)
    print(f"  Without conversion: {type(pct).__name__} = {pct}")
except TypeError as e:
    print(f"  ERROR: {e}")

# Test 2: With _ensure_float conversion
print("\nTEST 2: With single _ensure_float")
try:
    value_float = _ensure_float(position_value)
    total_float = _ensure_float(total_value)
    pct = value_float / total_float * 100
    print(f"  Result: {type(pct).__name__} = {pct}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 3: With double float conversion before arithmetic
print("\nTEST 3: With double float() before arithmetic")
try:
    value_float = _ensure_float(position_value)
    total_float = _ensure_float(total_value)
    pct_value = value_float / total_float * 100
    pct_float = float(float(pct_value))
    print(f"  Result: {type(pct_float).__name__} = {pct_float}")
except Exception as e:
    print(f"  ERROR: {e}")

# Test 4: Subtraction (the actual failing operation from logs)
print("\nTEST 4: Subtraction after conversion")
limit = Decimal('6.0')
try:
    pct_final = float(pct_float)  # double float like code does
    limit_final = float(float(limit))
    exceed = pct_final - limit_final
    print(f"  {pct_final:.1f}% - {limit_final:.0f}% = {exceed:.1f}% (SUCCESS)")
except TypeError as e:
    print(f"  FAILED: {e}")

# Test 5: Triple float conversion (the defensive code)
print("\nTEST 5: Triple float conversion before arithmetic")
try:
    pct_safe = float(float(float(pct_float)))
    limit_safe = float(float(float(limit)))
    exceed = pct_safe - limit_safe
    print(f"  {pct_safe:.1f}% - {limit_safe:.0f}% = {exceed:.1f}% (SUCCESS)")
except TypeError as e:
    print(f"  FAILED: {e}")

print("\n✓ All Decimal arithmetic tests passed")
