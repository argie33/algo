#!/usr/bin/env python3
"""Test end-to-end dashboard data flow from AWS API."""

import subprocess
import os
import sys

os.environ["AWS_PROFILE"] = "algo-developer"

# Get Terraform outputs
try:
    api_url = (
        subprocess.check_output(
            ["terraform", "output", "-raw", "api_url"],
            cwd="terraform",
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )
    pool_id = (
        subprocess.check_output(
            ["terraform", "output", "-raw", "cognito_user_pool_id"],
            cwd="terraform",
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )
    client_id = (
        subprocess.check_output(
            ["terraform", "output", "-raw", "cognito_user_pool_client_id"],
            cwd="terraform",
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )
except Exception as e:
    print(f"[ERROR] Failed to get Terraform outputs: {e}")
    sys.exit(1)

print("=" * 70)
print("DASHBOARD DATA FLOW TEST (AWS Endpoint Verification)")
print("=" * 70)
print(f"\nAPI Endpoint: {api_url}")
print(f"Cognito Pool: {pool_id}")

# Authenticate with Cognito
print("\n[1/3] Authenticating with Cognito...")
import boto3

cognito = boto3.client("cognito-idp", region_name="us-east-1")
try:
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": "edgebrookecapital@gmail.com",
            "PASSWORD": "TestPassword123!",
        },
    )
    token = auth["AuthenticationResult"]["AccessToken"]
    print("  [OK] Authenticated as edgebrookecapital@gmail.com")
    print(f"  Token: {token[:40]}...")
except Exception as e:
    print(f"  [ERROR] Cognito auth failed: {e}")
    sys.exit(1)

# Test protected endpoints
print("\n[2/3] Testing protected API endpoints...")
import requests

endpoints = [
    ("/api/algo/markets", "Market Data"),
    ("/api/algo/config", "Algo Configuration"),
    ("/api/algo/last-run", "Last Orchestrator Run"),
    ("/api/algo/exposure-policy", "Exposure Policy"),
    ("/api/algo/performance", "Performance Metrics"),
]

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
results = {}

for endpoint, name in endpoints:
    try:
        response = requests.get(f"{api_url}{endpoint}", headers=headers, timeout=5)
        status = response.status_code

        if status == 200:
            data = response.json()
            if isinstance(data, dict):
                if "data" in data:
                    result = "[OK] DATA"
                    results[name] = data["data"]
                elif "statusCode" in data and data["statusCode"] >= 400:
                    result = f"[ERROR] HTTP {data.get('statusCode')}"
                else:
                    result = "[OK]"
                    results[name] = data
            else:
                result = "[OK]"
        else:
            result = f"[ERROR] HTTP {status}"

        print(f"  {name:30} {result}")
    except Exception as e:
        print(f"  {name:30} [ERROR] {type(e).__name__}: {str(e)[:40]}")

# Display sample data
print("\n[3/3] Sample Data from AWS API:")
print("-" * 70)

if "Market Data" in results:
    print("\n[Market Data (showing first 5 fields)]")
    market = results["Market Data"]
    count = 0
    for key, value in market.items():
        if not key.startswith("_") and count < 5:
            if isinstance(value, (int, float)):
                print(f"  {key}: {value}")
            else:
                val_str = str(value)[:50]
                print(f"  {key}: {val_str}")
            count += 1

if "Last Orchestrator Run" in results:
    print("\n[Last Orchestrator Run]")
    run = results["Last Orchestrator Run"]
    for key in ["run_id", "success", "halted", "summary", "phases_completed"]:
        if key in run:
            print(f"  {key}: {run[key]}")

if "Algo Configuration" in results:
    print("\n[Algo Configuration (sample)]")
    cfg = results["Algo Configuration"]
    if "data" in cfg:
        cfg = cfg["data"]
    count = 0
    for key, value in cfg.items():
        if not key.startswith("_") and count < 5:
            print(f"  {key}: {value}")
            count += 1

if "Performance Metrics" in results:
    print("\n[Performance Metrics (sample)]")
    perf = results["Performance Metrics"]
    if "data" in perf:
        perf = perf["data"]
    count = 0
    for key, value in perf.items():
        if not key.startswith("_") and count < 5:
            print(f"  {key}: {value}")
            count += 1

print("\n" + "=" * 70)
print("[RESULT] END-TO-END DATA FLOW TEST")
print("=" * 70)
print("\nDashboard verification:")
print("  [OK] Can authenticate to Cognito with test user credentials")
print("  [CHECK] Can call protected API endpoints with Bearer token")
print("  [NOTE] API endpoint connectivity depends on Lambda deployment status")
if results:
    print("  [OK] API returns data from AWS")
else:
    print("  [WARNING] API returned errors (check Lambda/RDS health)")
print("\nNext: Run dashboard to display data")
print("  python tools/dashboard/dashboard.py")
print("=" * 70)
