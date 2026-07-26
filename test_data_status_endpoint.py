#!/usr/bin/env python3
"""Test data-status endpoint to find actual error."""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from utils.db import DatabaseContext  # noqa: E402

# Import market module to get _get_data_status function
spec = importlib.util.spec_from_file_location("market_module", "lambda/api/routes/algo_handlers/market.py")
market_module = importlib.util.module_from_spec(spec)
sys.modules['market_module'] = market_module
spec.loader.exec_module(market_module)

_get_data_status = market_module._get_data_status

try:
    print("Calling _get_data_status...")
    with DatabaseContext('read') as cur:
        result = _get_data_status(cur)
        print(f"✓ Success! Result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        if isinstance(result, dict) and 'summary' in result:
            print(f"Summary: {result['summary']}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    print("\nFull traceback:")
    traceback.print_exc()
