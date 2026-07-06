#!/usr/bin/env python3
"""Debug script to check specific endpoint errors in detail."""

import sys
import json
from zoneinfo import ZoneInfo

sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))

from dashboard.api_data_layer import api_call
from dashboard.fetchers_common import get_endpoint_path

ET = ZoneInfo("America/New_York")

FAILING_ENDPOINTS = ["activity", "audit", "cb", "exec_hist", "sec_rot", "sentiment", "sig_eval", "srank"]

print("=" * 80)
print("DETAILED ENDPOINT ERROR ANALYSIS")
print("=" * 80)
print()

for endpoint_name in FAILING_ENDPOINTS:
    endpoint_path = get_endpoint_path(endpoint_name)
    print(f"[{endpoint_name}] {endpoint_path}")
    print("-" * 80)

    try:
        response = api_call(endpoint_path)

        # Print full response
        if isinstance(response, dict):
            if "_error" in response:
                print(f"  ERROR: {response['_error']}")
            if "errorType" in response:
                print(f"  ERROR TYPE: {response['errorType']}")
            if "message" in response:
                print(f"  MESSAGE: {response['message']}")
            if "statusCode" in response:
                print(f"  STATUS CODE: {response['statusCode']}")

            # Print full response for debugging
            print(f"  FULL RESPONSE:")
            for key, value in sorted(response.items()):
                if isinstance(value, str) and len(str(value)) > 200:
                    print(f"    {key}: {str(value)[:200]}...")
                else:
                    print(f"    {key}: {value}")
        else:
            print(f"  RESPONSE (not dict): {response}")

    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")

    print()

print("=" * 80)
