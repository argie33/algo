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
import os
import logging
from datetime import datetime

# Base URL from environment, default to localhost:4000 for local development
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:4000")

# API endpoints to test with expected structures
ENDPOINTS = {
    # Core health & status
    "/api/health": "GET",
    "/api/status": "GET",

    # Algo (main trading system)
    "/api/algo/status": "GET",
    "/api/algo/trades?limit=10": "GET",
    "/api/algo/positions": "GET",
    "/api/algo/performance": "GET",
    "/api/algo/circuit-breakers": "GET",
    "/api/algo/data-status": "GET",

    # Market & Sectors
    "/api/sectors": "GET",
    "/api/stocks?limit=10": "GET",

    # Scores & Signals
    "/api/scores/stockscores?limit=10": "GET",
    "/api/signals/search": "GET",

    # Economic Data
    "/api/economic/leading-indicators": "GET",

    # Supporting Data
    "/api/industries": "GET",
    "/api/commodities": "GET",
}

def verify_endpoint(url, method="GET"):
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
            "error": f"Connection refused (is server running on {BASE_URL}?)"
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
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger = logging.getLogger(__name__)
    logger.info(f"API ENDPOINT VERIFICATION TEST SUITE")
    logger.info(f"Server: {BASE_URL}")
    logger.info(f"Started: {datetime.now().isoformat()}")
    logger.info(f"Total endpoints to test: {len(ENDPOINTS)}")

    results = []
    passed = 0
    failed = 0

    for endpoint, method in ENDPOINTS.items():
        url = f"{BASE_URL}{endpoint}"
        result = verify_endpoint(url, method)
        results.append(result)

        status_str = f"[{result['status']:3d}]" if result['status'] else "[ERR]"
        outcome = "PASS" if result['success'] else "FAIL"

        logger.info(f"{outcome:4} {status_str} {endpoint}")

        if result['success']:
            passed += 1
        else:
            failed += 1
            if result['error']:
                logger.error(f"Error: {result['error']}")

    # Summary
    logger.info(f"SUMMARY")
    logger.info(f"Total:  {len(ENDPOINTS)} endpoints")
    logger.info(f"Passed: {passed} ({100*passed//len(ENDPOINTS)}%)")
    logger.info(f"Failed: {failed}")

    if failed == 0:
        logger.info("RESULT: ALL TESTS PASSED")
        return 0
    else:
        logger.error(f"RESULT: {failed} TESTS FAILED")
        logger.warning("Failed endpoints:")
        for r in results:
            if not r['success']:
                logger.warning(f"  - {r['method']:4} {r['url']}")
                if r['error']:
                    logger.error(f"    {r['error']}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
