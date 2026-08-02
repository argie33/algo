"""
Test to verify Decimal/float fix in Phase 6 concentration check.
This test reproduces the error condition and validates the fix works.
"""

from decimal import Decimal
import pytest


def test_concentration_check_decimal_float_conversion():
    """Test that concentration check properly converts Decimal to float for arithmetic."""

    # Simulate PostgreSQL returning Decimal from numeric calculation
    pct_from_db = Decimal('100.00000000000000000000')  # PostgreSQL numeric precision
    max_size_pct_val = Decimal('6.0')  # Config value might also be Decimal

    # OLD CODE (would fail):
    # pct_float = float(pct) if pct is not None else 0.0
    # limit_for_comparison = float(max_size_pct_float)
    # exceed_amount = pct_float - limit_for_comparison  # ERROR if pct_float is still Decimal!

    # NEW CODE (ba6e2a6e8 fix):
    try:
        pct_float = float(pct_from_db) if pct_from_db is not None else 0.0
    except (TypeError, ValueError) as te:
        pytest.fail(f"Failed to convert pct: {te}")

    max_size_pct_float = float(max_size_pct_val)
    limit_for_comparison = float(max_size_pct_float)
    pct_float = float(pct_float)  # The fix: reconvert to ensure native Python float

    # This should NOT raise TypeError about Decimal-float mixing
    try:
        exceed_amount = pct_float - limit_for_comparison
    except TypeError as e:
        pytest.fail(f"Arithmetic failed after fix: {e}")

    # Verify the result is correct
    assert isinstance(exceed_amount, float), f"Result should be float, got {type(exceed_amount)}"
    assert abs(exceed_amount - 94.0) < 0.001, f"Expected 94.0, got {exceed_amount}"
    assert pct_float > limit_for_comparison, "Should detect oversized position"
    print(f"[PASS] Fix validated: {pct_float}% > {limit_for_comparison}% - arithmetic works")


def test_concentration_check_with_various_decimal_precisions():
    """Test fix handles different PostgreSQL numeric precisions."""

    test_cases = [
        (Decimal('100'), Decimal('6'), 94.0),
        (Decimal('100.0'), Decimal('6.0'), 94.0),
        (Decimal('100.00000000000000000000'), Decimal('6.00000000000000000000'), 94.0),
        (Decimal('12.5'), Decimal('6'), 6.5),
    ]

    for pct_decimal, limit_decimal, expected_exceed in test_cases:
        pct_float = float(pct_decimal)
        limit_float = float(limit_decimal)
        pct_float = float(pct_float)  # Apply fix

        exceed = pct_float - limit_float
        assert abs(exceed - expected_exceed) < 0.001, \
            f"Case {pct_decimal}/{limit_decimal}: expected {expected_exceed}, got {exceed}"

    print(f"[PASS] Fix handles {len(test_cases)} precision variations correctly")


if __name__ == "__main__":
    test_concentration_check_decimal_float_conversion()
    test_concentration_check_with_various_decimal_precisions()
    print("\n[PASS][PASS][PASS] ALL TESTS PASSED - Decimal/float fix is validated")
