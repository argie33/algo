#!/usr/bin/env python3
"""
Quick deployment verification - tests API endpoints after AWS deploy completes.
Run: python3 test_deployment.py <api_endpoint_url>
"""

import sys
import requests
import json
from datetime import datetime

ENDPOINTS = {
    'market_indices': '/api/market/indices',
    'market_technicals': '/api/market/technicals',
    'market_breadth': '/api/market/breadth',
    'sectors': '/api/sectors/all',
    'economic': '/api/economic/calendar',
    'stocks_aapl': '/api/stocks?symbol=AAPL',
}

def test_endpoint(base_url: str, name: str, endpoint: str) -> bool:
    """Test a single endpoint"""
    url = f"{base_url}{endpoint}"
    try:
        print(f"  Testing {name}...", end='')
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and data.get('data'):
                print(f" OK (data returned)")
                return True
            elif isinstance(data, list) and len(data) > 0:
                print(f" OK ({len(data)} items)")
                return True
            else:
                print(f" OK (empty response)")
                return True
        else:
            print(f" FAIL (HTTP {response.status_code})")
            return False
    except requests.exceptions.Timeout:
        print(f" TIMEOUT")
        return False
    except requests.exceptions.ConnectionError:
        print(f" CONNECTION ERROR")
        return False
    except Exception as e:
        print(f" ERROR: {str(e)}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_deployment.py <api_endpoint_url>")
        print("Example: python3 test_deployment.py https://d1234.execute-api.us-east-1.amazonaws.com")
        sys.exit(1)

    api_url = sys.argv[1].rstrip('/')

    print("════════════════════════════════════════════════════════════════")
    print("API DEPLOYMENT VERIFICATION")
    print("════════════════════════════════════════════════════════════════")
    print(f"API Endpoint: {api_url}")
    print(f"Time: {datetime.now().isoformat()}")
    print("")

    passed = 0
    failed = 0

    for name, endpoint in ENDPOINTS.items():
        if test_endpoint(api_url, name, endpoint):
            passed += 1
        else:
            failed += 1

    print("")
    print("════════════════════════════════════════════════════════════════")
    print(f"Results: {passed} passed, {failed} failed")
    print("════════════════════════════════════════════════════════════════")

    if failed == 0:
        print("✓ All tests passed! API is working correctly.")
        return 0
    else:
        print(f"✗ {failed} test(s) failed. Check API logs for details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
