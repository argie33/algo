#!/usr/bin/env python3
"""Load all 10,506 symbols to verify system works completely."""
import logging
from loaders.load_prices import PriceLoader
from utils.loaders.helpers import get_active_symbols

logging.basicConfig(level=logging.CRITICAL)

print("=== LOADING ALL 10,506 SYMBOLS ===\n")

try:
    symbols = list(get_active_symbols())
    print(f"Loading {len(symbols)} symbols...\n")

    loader = PriceLoader(interval="1d", asset_class="stock")
    result = loader.run(symbols, parallelism=2)

    print("LOAD RESULT:")
    print(f"  Rows inserted: {result.get('rows_inserted', 0):,}")
    print(f"  Circuit breaker triggered: {result.get('circuit_breaker_triggered', False)}")
    print(f"  Rate limit errors: {result.get('rate_limit_errors', 0)}")

    if not result.get('circuit_breaker_triggered'):
        print(f"\n[SUCCESS] Full load completed without circuit breaker!")
    else:
        print(f"\n[WARN] Circuit breaker was triggered")

except Exception as e:
    print(f"[ERROR] {e}")
