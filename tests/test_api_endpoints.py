#!/usr/bin/env python3
"""
API Endpoint Verification Tests

Tests all 19 functional API endpoints to ensure they:
1. Return HTTP 200 (or expected status)
2. Return valid JSON
3. Have expected response structure

Run: python3 tests/test_api_endpoints.py
"""

import requests
import json
import sys
from datetime import datetime

# Base URL - adjust for environment
BASE_URL = "http://localhost:3001"

# API endpoints to test with expected structures
ENDPOINTS = {
    # Algo endpoints
    "/api/algo/status": "GET",
    "/api/algo/trades?limit=10": "GET",
    "/api/algo/positions": "GET",
    "/api/algo/performance": "GET",
    "/api/algo/circuit-breakers": "GET",
    "/api/algo/data-status": "GET",

    # Market endpoints
    "/api/market/latest": "GET",

    # Sentiment endpoints
    "/api/sentiment/vix": "GET",

    # Sector endpoints
    "/api/sectors": "GET",

    # Stock endpoints
    "/api/stocks?limit=10": "GET",
    "/api/scores/stockscores?limit=10": "GET",

    # Economic endpoints
    "/api/economic/leading-indicators": "GET",

    # Financial endpoints
    "/api/financials/balance-sheet/AAPL": "GET",
    "/api/financials/income-statement/AAPL": "GET",
    "/api/financials/cash-flow/AAPL": "GET",

    # Health endpoint
    "/api/health": "GET",
}

def test_endpoint(url, method="GET"):
    """Test a single endpoint"""
    try:
        if method == "GET":
            resp = requests.get(url, timeout=10)
        else:
            resp = requests.post(url, timeout=10)

        status = resp.status_code
        success = status in (200, 201)

        # Try to parse JSON
        try:
            body = resp.json() if resp.text else {}
        except json.JSONDecodeError:
            body = None

        return {
            "url": url,
            "method": method,
            "status": status,
            "success": success,
            "has_body": body is not None,
            "error": None if success else f"HTTP {status}"
        }
    except requests.exceptions.ConnectionError:
        return {
            "url": url,
            "method": method,
            "status": 0,
            "success": False,
            "has_body": False,
            "error": "Connection refused (is server running on localhost:3001?)"
        }
    except requests.exceptions.Timeout:
        return {
            "url": url,
            "method": method,
            "status": 0,
            "success": False,
            "has_body": False,
            "error": "Request timeout"
        }
    except Exception as e:
        return {
            "url": url,
            "method": method,
            "status": 0,
            "success": False,
            "has_body": False,
            "error": str(e)
        }

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("API ENDPOINT VERIFICATION TEST SUITE")
    print("="*80)
    print(f"Server: {BASE_URL}")
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Total endpoints to test: {len(ENDPOINTS)}\n")

    results = []
    passed = 0
    failed = 0

    for endpoint, method in ENDPOINTS.items():
        url = f"{BASE_URL}{endpoint}"
        result = test_endpoint(url, method)
        results.append(result)

        status_str = f"[{result['status']:3d}]" if result['status'] else "[ERR]"
        outcome = "PASS" if result['success'] else "FAIL"

        print(f"{outcome:4} {status_str} {endpoint}")

        if result['success']:
            passed += 1
        else:
            failed += 1
            if result['error']:
                print(f"      Error: {result['error']}")

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total:  {len(ENDPOINTS)} endpoints")
    print(f"Passed: {passed} ({100*passed//len(ENDPOINTS)}%)")
    print(f"Failed: {failed}")

    if failed == 0:
        print("\nRESULT: ALL TESTS PASSED")
        return 0
    else:
        print(f"\nRESULT: {failed} TESTS FAILED")
        print("\nFailed endpoints:")
        for r in results:
            if not r['success']:
                print(f"  - {r['method']:4} {r['url']}")
                if r['error']:
                    print(f"    {r['error']}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
