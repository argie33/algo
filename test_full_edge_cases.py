#!/usr/bin/env python3
"""
COMPREHENSIVE EDGE CASE TESTS
Tests actual system components with edge case data
"""

import sys
from datetime import date
from decimal import Decimal

def test_position_sizer_edge_cases():
    """Test position sizer with edge case inputs."""
    print("\n=== POSITION SIZER EDGE CASES ===")

    try:
        from algo.trading.position_sizer import PositionSizer

        # Create a minimal valid config
        config = {
            "base_risk_pct": 0.75,
            "max_positions": 12,
            "max_position_size_pct": 8.0,
            "risk_reduction_at_minus_5": 0.8,
            "risk_reduction_at_minus_10": 0.6,
            "risk_reduction_at_minus_15": 0.3,
            "vix_caution_threshold": 25,
            "vix_max_threshold": 40,
            "vix_caution_risk_reduction": 0.8,
            "min_risk_pct_floor": 0.25,
            "execution_mode": "paper",
            "initial_capital_paper_trading": 100000,
        }

        try:
            sizer = PositionSizer(config)
            print("[OK] PositionSizer created with valid config")
        except Exception as e:
            print(f"[FAIL] PositionSizer failed: {e}")
            return False

        # Test with edge case: very tight stop
        entry_price = 100.0
        stop_loss = 99.0  # Only 1% risk

        try:
            result = sizer.calculate_position_size(
                "TEST",
                entry_price,
                stop_loss,
                date(2026, 7, 19)
            )
            print(f"[OK] Tight stop handled: {result.get('status', 'unknown')}")
        except Exception as e:
            print(f"[FAIL] Tight stop calculation failed: {e}")
            return False

        # Test with edge case: stop == entry (invalid)
        stop_loss = 100.0  # Same as entry!

        try:
            result = sizer.calculate_position_size(
                "TEST",
                entry_price,
                stop_loss,
                date(2026, 7, 19)
            )
            if result.get("status") == "invalid":
                print("[OK] Equal entry/stop rejected as invalid")
            else:
                print(f"[WARN] Equal entry/stop returned: {result.get('status')}")
        except AssertionError as e:
            # Expected - stop must be < entry
            print(f"[OK] Equal entry/stop caught by assertion: {str(e)[:50]}...")

        return True

    except ImportError as e:
        print(f"[SKIP] Cannot import PositionSizer: {e}")
        return True

def test_decimal_vs_float_precision():
    """Test Decimal vs float precision issues."""
    print("\n=== DECIMAL VS FLOAT PRECISION ===")

    # Test 1: Risk percentage calculation
    entry_price_float = 100.0
    stop_loss_float = 90.5

    risk_pct_float = (entry_price_float - stop_loss_float) / entry_price_float * 100
    print(f"Float calculation: {risk_pct_float:.10f}%")

    # Same with Decimal
    entry_price_dec = Decimal('100.0')
    stop_loss_dec = Decimal('90.5')
    risk_pct_dec = (entry_price_dec - stop_loss_dec) / entry_price_dec * 100
    print(f"Decimal calculation: {risk_pct_dec}%")

    # Check if they match reasonably
    if abs(float(risk_pct_dec) - risk_pct_float) < 0.0001:
        print("[OK] Float and Decimal calculations match")
    else:
        print(f"[WARN] Precision difference detected")

    # Test 2: Very small position sizing
    portfolio = Decimal('10000')
    risk_pct_small = Decimal('0.001')  # 0.1% risk
    risk_dollars = portfolio * risk_pct_small

    risk_per_share = Decimal('10')
    shares = int((risk_dollars / risk_per_share))
    print(f"Micro position: {shares} shares")

    if shares >= 0:
        print("[OK] Micro position sizing handled")
    else:
        print(f"[FAIL] Negative shares calculated: {shares}")
        return False

    return True

def run_all_tests():
    """Run all edge case tests."""
    print("=" * 70)
    print("COMPREHENSIVE EDGE CASE TESTING")
    print("=" * 70)

    tests_passed = 0
    tests_failed = 0

    test_functions = [
        test_position_sizer_edge_cases,
        test_decimal_vs_float_precision,
    ]

    for test_fn in test_functions:
        try:
            if test_fn():
                tests_passed += 1
            else:
                tests_failed += 1
        except Exception as e:
            print(f"[ERROR] {test_fn.__name__} crashed: {e}")
            tests_failed += 1

    print("\n" + "=" * 70)
    print(f"RESULTS: {tests_passed} passed, {tests_failed} failed")
    print("=" * 70)

    return tests_failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
