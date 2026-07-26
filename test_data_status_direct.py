#!/usr/bin/env python3
"""Test data-status function directly."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Load the market handler module directly
import importlib.util

spec = importlib.util.spec_from_file_location("market", "lambda/api/routes/algo_handlers/market.py")
market_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(market_module)

from utils.db import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        result = market_module._get_data_status(cur)
        print("✓ _get_data_status executed successfully!")
        print(f"Keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
        if isinstance(result, dict) and 'summary' in result:
            print(f"Summary: {result['summary']}")
except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
