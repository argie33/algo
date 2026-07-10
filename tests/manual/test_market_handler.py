#!/usr/bin/env python3
"""Test market endpoint directly."""
import os
import sys
import logging

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add paths
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api-pkg"))

try:
    # Import needed modules
    import psycopg2
    import psycopg2.extras
    from api_utils.database_context import DatabaseContext

    # Test directly with the handler
    from routes.algo_handlers.market import _get_markets
    from routes.utils import db_route_handler

    logger.info("[TEST] Testing _get_markets...")

    # Get a database cursor
    db = DatabaseContext('read')
    cur = db.__enter__()

    # Call the function
    logger.info("[TEST] Calling _get_markets...")
    result = _get_markets(cur)

    # Print result
    if isinstance(result, dict):
        if result.get("statusCode"):
            print(f"Status: {result.get('statusCode')}")
            if result.get("statusCode") >= 400:
                print(f"Error: {result}")
        else:
            import json
            print(f"Result: {json.dumps(result, indent=2, default=str)[:500]}")
    else:
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")

    db.__exit__(None, None, None)

except Exception as e:
    import traceback
    logger.error(f"Error: {e}")
    print(traceback.format_exc())
    sys.exit(1)
