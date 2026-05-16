#!/usr/bin/env python3
"""
Validate API response formats match frontend expectations.
Run after deployment to verify data is in correct format.

Usage:
    python3 validate_api_responses.py
"""

import requests
import json
import sys
from typing import Dict, Any, List

API_BASE = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

def test_health() -> bool:
    """Test health endpoint."""
    print("\n[1] Testing /api/health endpoint...")
    try:
        resp = requests.get(f"{API_BASE}/api/health", timeout=5)
        if resp.status_code != 200:
            print(f"  ✗ Expected 200, got {resp.status_code}")
            return False
        data = resp.json()
        if "data" not in data or "status" not in data["data"]:
            print(f"  ✗ Unexpected response format: {data}")
            return False
        print(f"  ✓ Health endpoint OK ({data['data']['status']})")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_algo_status() -> bool:
    """Test /api/algo/status endpoint."""
    print("\n[2] Testing /api/algo/status endpoint...")
    try:
        resp = requests.get(f"{API_BASE}/api/algo/status", timeout=5)
        if resp.status_code != 200:
            print(f"  ✗ Expected 200, got {resp.status_code}")
            if resp.status_code == 401:
                print(f"  ✗ Still getting 401 - Cognito auth not disabled yet!")
            return False
        data = resp.json()
        if "status" not in data:
            print(f"  ✗ Missing 'status' field in response: {data}")
            return False
        print(f"  ✓ Algo status OK (status={data['status']})")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_stock_scores() -> bool:
    """Test /api/scores/stockscores endpoint."""
    print("\n[3] Testing /api/scores/stockscores endpoint...")
    try:
        resp = requests.get(f"{API_BASE}/api/scores/stockscores?limit=5", timeout=10)
        if resp.status_code != 200:
            print(f"  ✗ Expected 200, got {resp.status_code}")
            return False

        data = resp.json()
        print(f"  Response keys: {list(data.keys())}")

        # Handle both response formats: {data: [...]} and {items: [...]}
        scores = data.get('data') or data.get('items')
        if not scores:
            print(f"  ✗ No data in response - expected either 'data' or 'items' key")
            return False

        if not isinstance(scores, list):
            print(f"  ✗ Data is not a list: {type(scores)}")
            return False

        if len(scores) == 0:
            print(f"  ⚠️  Data list is empty (loaders may not have run yet)")
            return True

        # Validate first item
        first = scores[0]
        required_fields = ['symbol', 'current_price', 'score']
        optional_fields = ['change_percent', 'market_cap', 'minervini_phase']

        print(f"  First item fields: {list(first.keys())}")

        # Check required fields
        missing = [f for f in required_fields if f not in first]
        if missing:
            print(f"  ✗ Missing required fields: {missing}")
            return False

        # Check optional fields
        missing_opt = [f for f in optional_fields if f not in first]
        if missing_opt:
            print(f"  ⚠️  Missing optional fields: {missing_opt}")

        # Validate field values
        if first['current_price'] is None:
            print(f"  ✗ current_price is None for {first['symbol']}")
            return False

        if first['score'] is None:
            print(f"  ✗ score is None for {first['symbol']}")
            return False

        print(f"  ✓ Stock scores OK - {len(scores)} items")
        print(f"    Sample: {first['symbol']} price=${first['current_price']} score={first['score']}")
        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_exposure_policy() -> bool:
    """Test /api/algo/exposure-policy endpoint."""
    print("\n[4] Testing /api/algo/exposure-policy endpoint...")
    try:
        resp = requests.get(f"{API_BASE}/api/algo/exposure-policy", timeout=5)
        if resp.status_code != 200:
            print(f"  ✗ Expected 200, got {resp.status_code}")
            return False

        data = resp.json()
        print(f"  Response keys: {list(data.keys())}")

        # Check for key fields (from the fix in Session 3)
        required_fields = ['exposure_pct', 'exposure_tier', 'is_entry_allowed', 'regime']

        missing = [f for f in required_fields if f not in data]
        if missing:
            print(f"  ✗ Missing required fields: {missing}")
            print(f"     (Fix: _get_exposure_policy() SQL query not updated)")
            return False

        print(f"  ✓ Exposure policy OK")
        print(f"    exposure_pct={data['exposure_pct']}, "
              f"tier={data['exposure_tier']}, "
              f"entry_allowed={data['is_entry_allowed']}")
        return True

    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=" * 70)
    print("API RESPONSE FORMAT VALIDATION")
    print("=" * 70)

    results = {
        "health": test_health(),
        "status": test_algo_status(),
        "scores": test_stock_scores(),
        "exposure": test_exposure_policy(),
    }

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All API responses are in correct format!")
        return 0
    else:
        print("\n❌ Some API responses failed validation - see details above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
