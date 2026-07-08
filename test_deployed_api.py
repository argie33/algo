#!/usr/bin/env python3
"""Test the deployed Lambda API to verify signals endpoint returns real data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import requests
import json
from datetime import datetime

# Test the deployed API Gateway endpoint
print("=" * 100)
print("TESTING DEPLOYED LAMBDA API")
print("=" * 100)

# The API Gateway endpoint from terraform
API_URL = "https://qz06d4y5n3.execute-api.us-east-1.amazonaws.com"

endpoints = [
    "/api/algo/signals",
    "/api/algo/positions",
    "/api/algo/scores",
]

print(f"\nTesting API at: {API_URL}\n")

for endpoint in endpoints:
    try:
        url = f"{API_URL}{endpoint}"
        print(f"[TEST] {endpoint}")

        response = requests.get(url, timeout=10)
        print(f"       Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # Check for data
            if isinstance(data, dict):
                if data.get("data"):
                    data_content = data.get("data")
                    if isinstance(data_content, list):
                        print(f"       Data: Array with {len(data_content)} items")
                        if data_content:
                            print(f"       Sample: {str(data_content[0])[:100]}")
                    elif isinstance(data_content, dict):
                        # For object responses
                        n = data_content.get("n")
                        total = data_content.get("total")
                        buy_sigs = data_content.get("buy_sigs", [])

                        if endpoint == "/api/algo/signals":
                            print(f"       Signals: n={n}, total={total}, buy_sigs count={len(buy_sigs)}")
                            if n == 0:
                                print(f"       ERROR: n=0 (hardcoded zeros NOT fixed!)")
                            else:
                                print(f"       SUCCESS: Real signals returned (n={n})")
                        elif endpoint == "/api/algo/scores":
                            top = data_content.get("top", [])
                            print(f"       Scores: {len(top)} items")
                        elif endpoint == "/api/algo/positions":
                            items = data_content.get("items", [])
                            print(f"       Positions: {len(items)} items")
            else:
                print(f"       Unexpected response type: {type(data)}")
        else:
            print(f"       Error: {response.text[:200]}")

    except requests.exceptions.ConnectionError:
        print(f"       CANNOT CONNECT - API Gateway might not be deployed or accessible")
    except Exception as e:
        print(f"       ERROR: {type(e).__name__}: {str(e)[:100]}")

print("\n" + "=" * 100)
print("VERIFICATION COMPLETE")
print("=" * 100)
