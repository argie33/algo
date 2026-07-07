#!/usr/bin/env python3
"""Diagnose why dashboard panels show unavailable."""
import sys
import os
import json

sys.path.insert(0, os.getcwd())

from dashboard.api_data_layer import set_cognito_auth, api_call
from dashboard.cognito_auth import CognitoAuth

# Step 1: Set up Cognito auth
print("=" * 70)
print("STEP 1: Cognito Authentication")
print("=" * 70)

cognito_user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
cognito_client_id = os.getenv('COGNITO_CLIENT_ID')
cognito_username = os.getenv('COGNITO_USERNAME')
cognito_password = os.getenv('COGNITO_PASSWORD')

print(f"User Pool ID: {cognito_user_pool_id}")
print(f"Client ID: {cognito_client_id}")
print(f"Username: {cognito_username}")
print(f"Password: {'SET' if cognito_password else 'NOT SET'}\n")

auth = CognitoAuth(cognito_user_pool_id, cognito_client_id)
if auth.authenticate(cognito_username, cognito_password):
    set_cognito_auth(auth)
    print("[OK] Cognito authentication successful\n")
else:
    print("[FAIL] Cognito authentication FAILED\n")
    sys.exit(1)

# Step 2: Test each API endpoint
print("=" * 70)
print("STEP 2: Testing API Endpoints")
print("=" * 70)

endpoints = [
    "/api/algo/portfolio",
    "/api/algo/positions",
    "/api/algo/performance",
    "/api/algo/markets",
    "/api/algo/config",
    "/api/algo/risk-metrics",
    "/api/algo/data-status",
    "/api/algo/last-run",
    "/api/algo/dashboard-signals",
    "/api/algo/trades",
    "/api/algo/circuit-breakers",
    "/api/scores",
]

results = {}
for endpoint in endpoints:
    try:
        data = api_call(endpoint)
        has_error = "_error" in data

        if has_error:
            error_msg = data["_error"]
            results[endpoint] = f"ERROR: {error_msg[:80]}"
            print(f"[FAIL] {endpoint}: {error_msg[:80]}")
        else:
            # Count fields
            field_count = len([k for k in data.keys() if not k.startswith('_')])
            status_code = data.get('statusCode', 'N/A')
            results[endpoint] = f"OK (fields={field_count})"
            print(f"[OK] {endpoint}: OK ({field_count} fields)")
    except Exception as e:
        results[endpoint] = f"EXCEPTION: {str(e)[:80]}"
        print(f"[FAIL] {endpoint}: {type(e).__name__}: {str(e)[:80]}")

# Step 3: Summary
print("\n" + "=" * 70)
print("STEP 3: Summary")
print("=" * 70)

errors = [r for r in results.values() if r.startswith("ERROR") or r.startswith("EXCEPTION")]
ok = [r for r in results.values() if r.startswith("OK")]

print(f"Working endpoints: {len(ok)}")
print(f"Failed endpoints: {len(errors)}")

if errors:
    print("\nFailed endpoints:")
    for endpoint, result in results.items():
        if not result.startswith("OK"):
            print(f"  {endpoint}: {result}")
