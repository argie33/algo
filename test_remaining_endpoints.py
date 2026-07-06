#!/usr/bin/env python3
"""Test remaining failing endpoints directly."""

import requests
import json

api_url = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
headers = {"Authorization": "Bearer dev-admin"}

endpoints = [
    ("/api/algo/circuit-breakers", "Circuit Breaker"),
    ("/api/algo/sentiment", "Sentiment"),
]

for path, name in endpoints:
    try:
        print(f"\n{'='*60}")
        print(f"{name}: {path}")
        print('='*60)

        resp = requests.get(f"{api_url}{path}", headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")

        try:
            data = resp.json()
            print(json.dumps(data, indent=2)[:800])
        except:
            print(f"Response: {resp.text[:200]}")

    except Exception as e:
        print(f"{name}: ERROR - {e}")
