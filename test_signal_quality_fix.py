#!/usr/bin/env python3
"""Test signal quality scorer fix."""

import sys
sys.path.insert(0, '/c/Users/arger/code/algo')

from loaders.load_signal_quality_scores import SignalQualityScoresLoader
from utils.loaders.helpers import get_active_symbols
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Testing SignalQualityScoresLoader with active symbols...")
print()

loader = SignalQualityScoresLoader()

# This is what Phase 7 should now be calling
all_symbols = get_active_symbols(timeout_secs=30)
print(f"Got {len(all_symbols)} active symbols")

try:
    result = loader.run(
        symbols=all_symbols[:100],  # Test with first 100 to keep it fast
        parallelism=4,
        backfill_days=1
    )

    print(f"\nResult: {result}")
    print(f"Success: {result.get('success')}")
    print(f"Symbols total: {result.get('symbols_total', 0)}")
    print(f"Symbols processed: {result.get('symbols_processed', 0)}")
    print(f"Rows inserted: {result.get('rows_inserted', 0)}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
