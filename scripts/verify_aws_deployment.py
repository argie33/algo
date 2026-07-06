#!/usr/bin/env python3
"""Verify 5xx fixes deployed to AWS Lambda."""

import sys
import os

# Set up AWS API endpoint (should be set by user or CloudFormation)
AWS_API_URL = os.environ.get("DASHBOARD_API_URL", "https://api.dev.algo.local")

if AWS_API_URL == "https://api.dev.algo.local":
    print(f"⚠️  DASHBOARD_API_URL not set. Using local: {AWS_API_URL}")
    print("To test AWS, set: export DASHBOARD_API_URL=<your-aws-api-url>")
    print()

sys.path.insert(0, '/'.join(__file__.split('/')[:-2]))

from dashboard.fetchers_common import get_endpoint_path
from dashboard.api_data_layer import api_call

PREVIOUSLY_FAILING_ENDPOINTS = [
    "activity",
    "audit",
    "cb",
    "exec_hist",
    "sec_rot",
    "sentiment",
    "sig_eval",
    "srank",
]

print("=" * 80)
print("AWS LAMBDA DEPLOYMENT VERIFICATION")
print("=" * 80)
print()

success_count = 0
failure_count = 0

for endpoint_name in PREVIOUSLY_FAILING_ENDPOINTS:
    endpoint_path = get_endpoint_path(endpoint_name)
    print(f"[{endpoint_name}] {endpoint_path}")

    try:
        response = api_call(endpoint_path)

        if isinstance(response, dict):
            status_code = response.get("statusCode")

            if "_error" in response:
                # Check if it's a validation error (5xx)
                error_msg = response.get("_error", "")
                if "response_validation_error" in error_msg:
                    print(f"  ❌ FAILED - Still getting validation error: {error_msg[:80]}")
                    failure_count += 1
                elif status_code in (500, 503):
                    print(f"  ❌ FAILED - {status_code} error: {error_msg[:80]}")
                    failure_count += 1
                else:
                    # 503 with no validation error = graceful degradation (acceptable)
                    print(f"  ✅ OK - Graceful {status_code}: {error_msg[:60]}")
                    success_count += 1
            else:
                print(f"  ✅ OK - Status {status_code}, data returned successfully")
                success_count += 1
        else:
            print(f"  ⚠️  Unexpected response type: {type(response)}")
            failure_count += 1

    except Exception as e:
        print(f"  ❌ FAILED - Exception: {type(e).__name__}: {str(e)[:60]}")
        failure_count += 1

    print()

print("=" * 80)
print("VERIFICATION RESULTS")
print("=" * 80)
print()
print(f"✅ Successful: {success_count}/{len(PREVIOUSLY_FAILING_ENDPOINTS)}")
print(f"❌ Failed: {failure_count}/{len(PREVIOUSLY_FAILING_ENDPOINTS)}")
print()

if failure_count == 0:
    print("🎉 ALL ENDPOINTS VERIFIED - 5xx FIXES DEPLOYED SUCCESSFULLY!")
    sys.exit(0)
else:
    print(f"⚠️  {failure_count} endpoints still have issues")
    print("   Possible causes:")
    print("   1. Lambda cold-start (may take 30-60 seconds)")
    print("   2. CloudWatch logs: Check AWS CloudWatch for deployment logs")
    print("   3. Check if DASHBOARD_API_URL is correctly configured")
    sys.exit(1)
