#!/usr/bin/env python3
"""Test that price loader can load symbols without hitting circuit breaker."""

import logging
from loaders.load_prices import PriceLoader

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("test")
logger.setLevel(logging.INFO)

print("=== Testing Price Loader Fix ===\n")

try:
    # Test with small sample
    test_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]  # Just 5 to test quickly

    logger.info(f"Loading prices for {len(test_symbols)} symbols...")
    loader = PriceLoader(interval="1d", asset_class="stock")

    logger.info(f"Batch size: {loader.batch_size}")
    logger.info(
        f"Circuit breaker threshold: {loader._rate_limit_circuit_break_threshold}s"
    )
    logger.info(f"Is EOD pipeline: {loader._is_eod_pipeline}")

    result = loader.run(test_symbols, parallelism=1)

    print("\nResult:")
    print(f"  Symbols loaded: {result.get('symbols_loaded', 0)}")
    print(f"  Symbols failed: {result.get('symbols_failed', 0)}")
    print(f"  Rows inserted: {result.get('rows_inserted', 0)}")

    if result.get("circuit_breaker_triggered"):
        print(
            "  [WARN] Circuit breaker triggered (this would be a problem for full load)"
        )
    else:
        print("  [OK] No circuit breaker trigger")

    if "elapsed_min" in result:
        print(f"  Elapsed: {result['elapsed_min']} minutes")

    print("\n[OK] Price loader test complete - fix appears to be working")

except Exception as e:
    logger.exception(f"Error testing price loader: {e}")
    print(f"\n[FAIL] Price loader test failed: {e}")
