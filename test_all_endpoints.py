#!/usr/bin/env python3
"""
Comprehensive endpoint test suite to verify all 4xx/5xx errors are fixed.
This must be run AFTER deployment to test against the live API.

Usage:
    python3 test_all_endpoints.py <API_URL> <JWT_TOKEN>

Example:
    python3 test_all_endpoints.py https://api.example.com eyJhbGc...
"""

import sys
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

class APITester:
    def __init__(self, base_url: str, jwt_token: str = None):
        self.base_url = base_url.rstrip('/')
        self.jwt_token = jwt_token
        self.headers = {'Content-Type': 'application/json'}
        if jwt_token:
            self.headers['Authorization'] = f'Bearer {jwt_token}'
        self.results = []
        self.errors = []

    def test_endpoint(self, method: str, path: str, params: Dict = None,
                     expected_status: int = 200, name: str = None) -> Tuple[bool, str]:
        """Test a single endpoint and record result."""
        test_name = name or f"{method} {path}"
        url = f"{self.base_url}{path}"

        try:
            if method == 'GET':
                resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            elif method == 'POST':
                resp = requests.post(url, headers=self.headers, json=params or {}, timeout=10)
            else:
                return False, f"Unknown method: {method}"

            status_ok = resp.status_code == expected_status
            message = f"{test_name}: {resp.status_code}"

            if status_ok:
                self.results.append((test_name, resp.status_code, 'PASS'))
                return True, message
            else:
                self.errors.append((test_name, resp.status_code, resp.text[:200]))
                self.results.append((test_name, resp.status_code, 'FAIL'))
                return False, message

        except Exception as e:
            self.errors.append((test_name, 'ERROR', str(e)[:200]))
            self.results.append((test_name, 'ERROR', 'FAIL'))
            return False, f"{test_name}: {type(e).__name__}"

    def run_tests(self):
        """Run comprehensive endpoint tests."""
        print("\n" + "="*80)
        print("COMPREHENSIVE API ENDPOINT TEST SUITE")
        print("="*80 + "\n")

        # PUBLIC ENDPOINTS (no auth required)
        print("PUBLIC ENDPOINTS (no auth required)")
        print("-" * 80)
        self.test_endpoint('GET', '/api/health', name="Health check")

        # PROTECTED ENDPOINTS (require auth)
        if not self.jwt_token:
            print("\nWARNING: No JWT token provided. Skipping protected endpoints.")
            print("To test protected endpoints, run with: python3 test_all_endpoints.py <URL> <TOKEN>\n")
        else:
            print("\nPROTECTED ENDPOINTS (auth required)")
            print("-" * 80)

            # Algo endpoints
            self.test_endpoint('GET', '/api/algo/status', name="Algo status")
            self.test_endpoint('GET', '/api/algo/trades', name="Algo trades")
            self.test_endpoint('GET', '/api/algo/positions', name="Algo positions")
            self.test_endpoint('GET', '/api/algo/performance', name="Algo performance")
            self.test_endpoint('GET', '/api/algo/circuit-breakers', name="Circuit breakers")
            self.test_endpoint('GET', '/api/algo/equity-curve', name="Equity curve")
            self.test_endpoint('GET', '/api/algo/data-status', name="Data status")

            # Sector endpoints
            self.test_endpoint('GET', '/api/sectors', name="Sectors list")
            self.test_endpoint('GET', '/api/sectors/Technology', name="Sector detail")
            self.test_endpoint('GET', '/api/sectors/Technology/trend', name="Sector trend")

            # Industry endpoints
            self.test_endpoint('GET', '/api/industries', name="Industries list")
            self.test_endpoint('GET', '/api/industries/Software', name="Industry detail")

            # Signal endpoints
            self.test_endpoint('GET', '/api/signals', name="Signals")

            # Price endpoints
            self.test_endpoint('GET', '/api/prices', params={'symbol': 'AAPL'}, name="Prices")

            # Stock endpoints
            self.test_endpoint('GET', '/api/stocks', name="Stocks")

            # Market endpoints
            self.test_endpoint('GET', '/api/market', name="Market data")

            # Scores endpoints
            self.test_endpoint('GET', '/api/scores', name="Scores")

        print("\n" + "="*80)
        print("TEST RESULTS SUMMARY")
        print("="*80 + "\n")

        passed = sum(1 for _, _, status in self.results if status == 'PASS')
        failed = sum(1 for _, _, status in self.results if status == 'FAIL')

        print(f"Total tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if self.errors:
            print(f"\nERRORS FOUND ({len(self.errors)}):")
            print("-" * 80)
            for test_name, status, error in self.errors:
                print(f"\n{test_name}")
                print(f"  Status: {status}")
                print(f"  Error: {error}")

        print("\n" + "="*80)

        # Check for 5xx errors (should be none)
        fatal_errors = [
            (name, code) for name, code, status in self.results
            if isinstance(code, int) and 500 <= code < 600
        ]

        if fatal_errors:
            print("CRITICAL: 5xx errors found!")
            for name, code in fatal_errors:
                print(f"  {name}: {code}")
            return False

        # Check for unexpected 4xx errors
        config_errors = [
            (name, code) for name, code, status in self.results
            if isinstance(code, int) and 400 <= code < 500
            and code not in [401, 403, 404, 429]  # Expected errors
        ]

        if config_errors:
            print("WARNING: Unexpected 4xx errors found!")
            for name, code in config_errors:
                print(f"  {name}: {code}")

        return failed == 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_all_endpoints.py <API_URL> [JWT_TOKEN]")
        print("Example: python3 test_all_endpoints.py https://api.example.com eyJhbGc...")
        sys.exit(1)

    base_url = sys.argv[1]
    jwt_token = sys.argv[2] if len(sys.argv) > 2 else None

    tester = APITester(base_url, jwt_token)
    success = tester.run_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
