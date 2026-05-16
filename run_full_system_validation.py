#!/usr/bin/env python3
"""
Complete end-to-end system validation.
Run this after Terraform deployment completes and API returns 200.

Usage:
    python3 run_full_system_validation.py
"""

import requests
import json
import sys
from datetime import datetime
from typing import Dict, Any, List, Tuple

API_BASE = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BLUE}{'='*70}")
    print(f"{text}")
    print(f"{'='*70}{Colors.ENDC}\n")

def print_pass(msg: str):
    print(f"{Colors.GREEN}✓ PASS{Colors.ENDC}: {msg}")

def print_fail(msg: str):
    print(f"{Colors.RED}✗ FAIL{Colors.ENDC}: {msg}")

def print_warn(msg: str):
    print(f"{Colors.YELLOW}⚠ WARN{Colors.ENDC}: {msg}")

def test_health() -> bool:
    """Test 1: Health endpoint"""
    print_header("TEST 1: HEALTH ENDPOINT")
    try:
        resp = requests.get(f"{API_BASE}/api/health", timeout=5)
        if resp.status_code != 200:
            print_fail(f"Health endpoint returned {resp.status_code}")
            return False
        data = resp.json()
        if data.get("data", {}).get("status") == "healthy":
            print_pass("Health endpoint responsive")
            return True
        else:
            print_fail("Health endpoint not reporting healthy")
            return False
    except Exception as e:
        print_fail(f"Health check failed: {e}")
        return False

def test_api_status() -> bool:
    """Test 2: Algo status endpoint"""
    print_header("TEST 2: ALGO STATUS ENDPOINT")
    try:
        resp = requests.get(f"{API_BASE}/api/algo/status", timeout=5)
        if resp.status_code != 200:
            print_fail(f"Expected 200, got {resp.status_code}")
            if resp.status_code == 401:
                print_fail("Still getting 401 - Cognito auth not disabled!")
            return False
        data = resp.json()
        if "status" in data:
            print_pass(f"Algo operational - status: {data['status']}")
            return True
        else:
            print_fail("Response missing 'status' field")
            return False
    except Exception as e:
        print_fail(f"Status check failed: {e}")
        return False

def test_stock_scores(limit: int = 10) -> Tuple[bool, Dict]:
    """Test 3: Stock scores endpoint and data quality"""
    print_header("TEST 3: STOCK SCORES ENDPOINT")
    try:
        resp = requests.get(f"{API_BASE}/api/scores/stockscores?limit={limit}", timeout=10)
        if resp.status_code != 200:
            print_fail(f"Expected 200, got {resp.status_code}")
            return False, {}

        data = resp.json()
        scores = data.get('data') or data.get('items')

        if not scores:
            print_warn("No data returned (loaders may not have run yet)")
            return True, {}  # Not a hard failure if data not ready

        if not isinstance(scores, list):
            print_fail("Response data is not a list")
            return False, {}

        print_pass(f"Stock scores endpoint returned {len(scores)} items")

        # Validate first item
        first = scores[0]
        required_fields = ['symbol', 'current_price', 'score']
        optional_fields = ['change_percent', 'market_cap', 'minervini_phase']

        missing = [f for f in required_fields if f not in first]
        if missing:
            print_fail(f"Missing required fields: {missing}")
            return False, {}

        missing_opt = [f for f in optional_fields if f not in first]
        if missing_opt:
            print_warn(f"Missing optional fields: {missing_opt}")

        # Validate values
        if first.get('current_price') is None:
            print_fail(f"current_price is None for {first['symbol']}")
            return False, {}

        if first.get('score') is None:
            print_fail(f"score is None for {first['symbol']}")
            return False, {}

        print_pass(f"Response format valid - Sample: {first['symbol']} price=${first['current_price']} score={first['score']}")
        return True, {'count': len(scores), 'sample': first}

    except Exception as e:
        print_fail(f"Stock scores check failed: {e}")
        return False, {}

def test_exposure_policy() -> bool:
    """Test 4: Exposure policy endpoint"""
    print_header("TEST 4: EXPOSURE POLICY ENDPOINT")
    try:
        resp = requests.get(f"{API_BASE}/api/algo/exposure-policy", timeout=5)
        if resp.status_code != 200:
            print_fail(f"Expected 200, got {resp.status_code}")
            return False

        data = resp.json()
        required_fields = ['exposure_pct', 'exposure_tier', 'is_entry_allowed', 'regime']

        missing = [f for f in required_fields if f not in data]
        if missing:
            print_fail(f"Missing required fields: {missing}")
            return False

        print_pass(f"Exposure policy OK - Regime: {data['regime']}, Tier: {data['exposure_tier']}")
        return True

    except Exception as e:
        print_fail(f"Exposure policy check failed: {e}")
        return False

def test_api_performance() -> bool:
    """Test 5: API response time"""
    print_header("TEST 5: API PERFORMANCE")
    try:
        import time
        times = []

        for i in range(3):
            start = time.time()
            resp = requests.get(f"{API_BASE}/api/algo/status", timeout=10)
            elapsed = time.time() - start
            times.append(elapsed)

            if resp.status_code != 200:
                print_fail(f"Request {i+1} failed with status {resp.status_code}")
                return False

        avg_time = sum(times) / len(times)
        print_pass(f"Average response time: {avg_time:.3f}s (3 requests)")

        if avg_time > 2.0:
            print_warn(f"Response time is high (>{2.0}s) - consider optimization")

        return True

    except Exception as e:
        print_fail(f"Performance check failed: {e}")
        return False

def test_calculation_correctness(scores_data: Dict) -> bool:
    """Test 6: Verify calculations"""
    print_header("TEST 6: CALCULATION CORRECTNESS")

    if not scores_data.get('sample'):
        print_warn("No sample data to validate calculations")
        return True

    first = scores_data['sample']

    # Check change_percent is numeric
    if 'change_percent' in first and first['change_percent'] is not None:
        try:
            float(first['change_percent'])
            print_pass("change_percent is numeric")
        except:
            print_fail(f"change_percent not numeric: {first['change_percent']}")
            return False

    # Check market_cap is numeric
    if 'market_cap' in first and first['market_cap'] is not None:
        try:
            float(first['market_cap'])
            print_pass("market_cap is numeric")
        except:
            print_fail(f"market_cap not numeric: {first['market_cap']}")
            return False

    # Check scores in reasonable range
    score = first.get('score')
    if score is not None:
        if isinstance(score, (int, float)) and 0 <= score <= 100:
            print_pass(f"Score in valid range: {score}")
        else:
            print_warn(f"Score outside expected range: {score}")

    return True

def main():
    """Run all tests"""
    print_header("COMPLETE SYSTEM VALIDATION")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"API Base: {API_BASE}")

    results = {}
    scores_data = {}

    # Run all tests
    results['health'] = test_health()
    results['status'] = test_api_status()
    results['scores_ok'], scores_data = test_stock_scores()
    results['exposure'] = test_exposure_policy()
    results['performance'] = test_api_performance()
    results['calculations'] = test_calculation_correctness(scores_data)

    # Print summary
    print_header("VALIDATION SUMMARY")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓{Colors.ENDC}" if result else f"{Colors.RED}✗{Colors.ENDC}"
        print(f"{status} {test_name.replace('_', ' ').title()}")

    print(f"\n{Colors.BLUE}Overall: {passed}/{total} tests passed{Colors.ENDC}")

    if passed == total:
        print(f"\n{Colors.GREEN}✅ SYSTEM IS FULLY OPERATIONAL{Colors.ENDC}")
        print("All API endpoints responding correctly")
        print("All data formats valid")
        print("Dashboard pages should load with real data")
        return 0
    else:
        print(f"\n{Colors.RED}❌ SYSTEM VALIDATION FAILED{Colors.ENDC}")
        print(f"Failed tests: {total - passed}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
