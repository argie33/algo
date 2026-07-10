#!/usr/bin/env python3
"""Test full API routing flow."""
import os
import sys
import json
import logging

os.environ["LOCAL_MODE"] = "true"
os.environ["ENVIRONMENT"] = "development"
os.environ.pop("COGNITO_USER_POOL_ID", None)
os.environ.pop("COGNITO_CLIENT_ID", None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api-pkg"))

try:
    from api_utils.database_context import DatabaseContext
    import api_router

    logger.info("[TEST] Testing full API route...")

    # Get database cursor
    db = DatabaseContext('read')
    cur = db.__enter__()

    # Call api_router.route_request like the lambda_handler does
    logger.info("[TEST] Calling api_router.route_request('GET', '/api/algo/markets', {}, None)...")
    response = api_router.route_request(cur, "/api/algo/markets", "GET", {}, None, jwt_claims=None)

    # Print response
    print(f"\n[RESPONSE]")
    print(f"Type: {type(response)}")
    if isinstance(response, dict):
        print(f"statusCode: {response.get('statusCode')}")
        if response.get('statusCode') >= 400:
            print(f"Full response: {json.dumps(response, indent=2, default=str)}")
        else:
            # Just show keys if success
            print(f"Keys: {list(response.keys())}")
            if 'data' in response and isinstance(response['data'], dict):
                print(f"Data keys: {list(response['data'].keys())[:10]}")
    else:
        print(f"Value: {response}")

    db.__exit__(None, None, None)

except Exception as e:
    import traceback
    logger.error(f"Error: {e}")
    print(f"\n[ERROR] {traceback.format_exc()}")
    sys.exit(1)
