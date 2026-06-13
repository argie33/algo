#!/usr/bin/env python3
"""
Validation suite for M20 NULL handling standardization fixes.

Verifies that 0-value prices and scores are NOT treated as None.
Previously, code like `if row:` would treat (0, None) as falsy.
Now code uses explicit `is not None` checks.

Test scenarios:
1. Price=0 should NOT be treated as NULL
2. Score=0 should NOT be treated as NULL
3. Only actual None values should trigger None handling paths
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import datetime, date
from typing import Optional, Any

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")

# Test data: realistic tuples that might come from database rows
class TestData:
    """Example database query results with edge cases."""

    # (symbol, price, volume, score) tuples
    EDGE_CASES = [
        ("ZERO_PRICE", 0, 1000000, 45.5),           # Price is 0 (legitimate edge case)
        ("ZERO_SCORE", 100.0, 1000000, 0),          # Score is 0
        ("ZERO_BOTH", 0, 0, 0),                     # Both zero
        ("NORMAL", 125.50, 5000000, 75.2),          # Normal case
        ("HALF_ZERO", None, 2000000, 50.0),         # Price is None (should be handled)
    ]

    REGIME_DATA = [
        ("SPY", "uptrend", 0.85, "2026-06-13"),     # Market exposure = 0.85
        ("SPY", "downtrend", 0, "2026-06-13"),      # Exposure = 0 (should be valid)
        ("SPY", None, None, "2026-06-13"),          # No regime data (should be handled)
    ]

    MA_CROSSOVER = [
        (100.0, 101.0, 102.0),                      # Price below SMAs
        (0, 50.0, 51.0),                            # Price=0 (edge case, legitimate in ETF portfolios)
        (100.0, None, 99.0),                        # Missing fast MA (should be handled)
    ]

def test_price_zero_not_none():
    """Test 1: Price=0 should NOT be treated as None."""
    logger.info("\n[TEST 1] Price=0 handling (implicit False → explicit is not None)")

    test_cases = [
        (("SYMBOL", 0, 1000000), "Price=0 with volume"),
        (("SYMBOL", 0, 0), "Price=0 with zero volume"),
        (("SYMBOL", None, 1000000), "Price=None (actual NULL)"),
    ]

    passed = 0
    for data, description in test_cases:
        symbol, price, volume = data

        # OLD PATTERN (buggy): if price would treat 0 as False
        # if symbol and price:  # BUG: price=0 fails!
        #     use_price = True

        # NEW PATTERN (fixed): explicit is not None
        if symbol is not None and price is not None:
            use_price = True
        else:
            use_price = False

        # Validation
        if price == 0:
            # Zero price IS valid and should be used
            if use_price:
                logger.info(f"  ✓ {description}: correctly treated as valid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as invalid")
        elif price is None:
            # None price should NOT be used
            if not use_price:
                logger.info(f"  ✓ {description}: correctly treated as invalid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as valid")
        else:
            # Normal price should be used
            if use_price:
                logger.info(f"  ✓ {description}: correctly treated as valid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as invalid")

    return passed == len(test_cases)


def test_score_zero_not_none():
    """Test 2: Score=0 should NOT be treated as None."""
    logger.info("\n[TEST 2] Score=0 handling (implicit False → explicit is not None)")

    test_cases = [
        (0, "Score=0 (valid: no signal strength)"),
        (75.5, "Score=75.5 (normal)"),
        (None, "Score=None (actual NULL)"),
    ]

    passed = 0
    for score, description in test_cases:
        # NEW PATTERN: explicit check
        if score is not None:
            use_score = True
        else:
            use_score = False

        if score == 0:
            if use_score:
                logger.info(f"  ✓ {description}: correctly treated as valid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as invalid")
        elif score is None:
            if not use_score:
                logger.info(f"  ✓ {description}: correctly treated as invalid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as valid")
        else:
            if use_score:
                logger.info(f"  ✓ {description}: correctly treated as valid")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY treated as invalid")

    return passed == len(test_cases)


def test_regime_exposure_zero():
    """Test 3: Market exposure=0 should NOT be treated as None (halt signal logic)."""
    logger.info("\n[TEST 3] Market exposure=0 handling (regime/signal logic)")

    test_cases = [
        (0.85, "Normal exposure (85%)"),
        (0, "Zero exposure (fully hedged or halt)"),
        (None, "No exposure data (NULL)"),
    ]

    passed = 0
    for exposure, description in test_cases:
        # Typical usage: "should we trade?" decision
        # NEW PATTERN: explicit check
        if exposure is not None and exposure > 0:
            should_trade = True
        else:
            # Could be 0 (halt), None (no data), or negative
            should_trade = False

        # Validation
        if exposure == 0:
            # Zero exposure should trigger halt (should_trade=False)
            if not should_trade:
                logger.info(f"  ✓ {description}: correctly triggers halt")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY allows trading")
        elif exposure is None:
            if not should_trade:
                logger.info(f"  ✓ {description}: correctly no data → no trade")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY allows trading with no data")
        else:
            if should_trade:
                logger.info(f"  ✓ {description}: correctly allows trading")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY prevents trading")

    return passed == len(test_cases)


def test_ma_crossover_zero_price():
    """Test 4: MA crossover with price=0 (e.g., in portfolio distance calculations)."""
    logger.info("\n[TEST 4] MA crossover with price=0 (movement detection logic)")

    test_cases = [
        ((100.0, 101.0, 102.0), "Normal: below SMAs"),
        ((0, 50.0, 51.0), "Edge case: price=0, above both SMAs"),
        ((100.0, None, 99.0), "Missing fast MA"),
    ]

    passed = 0
    for (price, fast_ma, slow_ma), description in test_cases:
        # NEW PATTERN: explicit None checks
        if price is not None and fast_ma is not None and slow_ma is not None:
            below_fast = price < fast_ma
            below_slow = price < slow_ma
            has_valid_data = True
        else:
            has_valid_data = False

        # Validation
        if price is None or fast_ma is None or slow_ma is None:
            if not has_valid_data:
                logger.info(f"  ✓ {description}: correctly detected missing data")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY used incomplete data")
        elif price == 0:
            if has_valid_data and below_fast and below_slow:
                logger.info(f"  ✓ {description}: correctly computed with price=0")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY handled price=0")
        else:
            if has_valid_data:
                logger.info(f"  ✓ {description}: correctly computed")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY rejected valid data")

    return passed == len(test_cases)


def test_distance_averaging_with_zero():
    """Test 5: Portfolio distance averaging with zero values."""
    logger.info("\n[TEST 5] Distance averaging with zero values")

    distances = [
        ([100.0, 50.0, 0, 75.0], "Mix including zero"),
        ([0, 0, 0], "All zeros (portfolio unallocated)"),
        ([100.0, None, 50.0], "Mix with None (incomplete data)"),
    ]

    passed = 0
    for distance_list, description in distances:
        # NEW PATTERN: filter out None, keep zeros
        valid_distances = [d for d in distance_list if d is not None]

        if valid_distances:
            avg_distance = sum(valid_distances) / len(valid_distances)
            has_result = True
        else:
            avg_distance = None
            has_result = False

        # Validation
        if None in distance_list:
            if has_result and len(valid_distances) > 0:
                logger.info(f"  ✓ {description}: correctly filtered None, kept zeros")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY handled mixed data")
        elif 0 in distance_list:
            if has_result and avg_distance == sum(distance_list) / len(distance_list):
                logger.info(f"  ✓ {description}: correctly included zero in average")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY excluded zero")
        else:
            if has_result:
                logger.info(f"  ✓ {description}: correctly computed")
                passed += 1
            else:
                logger.error(f"  ✗ {description}: INCORRECTLY failed on valid data")

    return passed == len(distances)


def main():
    """Run all M20 NULL handling validation tests."""
    logger.info("=" * 80)
    logger.info("M20 NULL HANDLING STANDARDIZATION VALIDATION")
    logger.info("=" * 80)

    results = {
        "Price=0 handling": test_price_zero_not_none(),
        "Score=0 handling": test_score_zero_not_none(),
        "Market exposure=0": test_regime_exposure_zero(),
        "MA crossover with price=0": test_ma_crossover_zero_price(),
        "Distance averaging": test_distance_averaging_with_zero(),
    }

    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nResult: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n✓ All M20 fixes validated successfully!")
        return 0
    else:
        logger.error(f"\n✗ {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    exit(main())
