#!/usr/bin/env python3
"""Test market endpoint directly to see actual error."""
import os
import sys
import logging

# Set local mode
os.environ["LOCAL_MODE"] = "true"
os.environ["ALLOW_STALE_PORTFOLIO_DATA"] = "true"

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Add api-pkg to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api-pkg"))

try:
    # Don't import handler, just test the market endpoint
    from routes.algo_handlers.market import _get_markets
    from api_utils.database_context import DatabaseContext

    # Test database connection
    print("Testing database connection...")
    db = DatabaseContext('read')
    print("[OK] Database connection works")

    # Test _get_markets directly
    print("\n[TEST] Testing _get_markets function...")
    cur = db.cursor()
    result = _get_markets(cur)
    print(f"Result: {result}")
    db.close()

except Exception as e:
    import traceback
    print(f"Error: {e}")
    print(traceback.format_exc())
    sys.exit(1)
