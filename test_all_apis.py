#!/usr/bin/env python3
"""
Comprehensive API Testing Suite
Tests all endpoints and identifies issues
"""
import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:3001"
TIMEOUT = 10

class APITester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.results = []
        self.passed = 0
        self.failed = 0

    def test_endpoint(self, method, endpoint, name, expected_status=200):
        """Test a single endpoint"""
        try:
            url = f"{self.base_url}{endpoint}"
            start = time.time()

            if method == "GET":
                response = requests.get(url, timeout=TIMEOUT)
            else:
                response = requests.post(url, timeout=TIMEOUT)

            elapsed = (time.time() - start) * 1000  # ms

            # Check response
            success = response.status_code == expected_status
            status_ok = "✅" if success else "❌"

            # Try to parse JSON
            try:
                data = response.json()
                data_size = len(json.dumps(data))
            except:
                data = None
                data_size = len(response.text)

            result = {
                'endpoint': endpoint,
                'name': name,
                'method': method,
                'status': response.status_code,
                'expected': expected_status,
                'success': success,
                'elapsed_ms': elapsed,
                'data_bytes': data_size,
                'data': data
            }

            self.results.append(result)

            if success:
                self.passed += 1
                print(f"{status_ok} {method:4s} {endpoint:50s} | {response.status_code} | {elapsed:6.0f}ms | {data_size:8d}B")
            else:
                self.failed += 1
                print(f"{status_ok} {method:4s} {endpoint:50s} | {response.status_code} (expected {expected_status}) | {elapsed:6.0f}ms")
                if data:
                    print(f"   Error: {data}")

            return result

        except requests.exceptions.Timeout:
            self.failed += 1
            print(f"❌ {method:4s} {endpoint:50s} | TIMEOUT after {TIMEOUT}s")
            return None
        except requests.exceptions.ConnectionError:
            self.failed += 1
            print(f"❌ {method:4s} {endpoint:50s} | CONNECTION ERROR")
            return None
        except Exception as e:
            self.failed += 1
            print(f"❌ {method:4s} {endpoint:50s} | ERROR: {str(e)}")
            return None

    def run_all_tests(self):
        """Run all API tests"""
        print("\n" + "="*100)
        print("API ENDPOINT TESTING - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("="*100 + "\n")

        # Health checks
        print("📋 HEALTH CHECKS")
        print("-"*100)
        self.test_endpoint("GET", "/health", "Health Check")
        self.test_endpoint("GET", "/api/health", "API Health Check")
        print()

        # Stock Scores endpoints
        print("📊 STOCK SCORES ENDPOINTS")
        print("-"*100)
        self.test_endpoint("GET", "/api/scores", "All Stock Scores")
        self.test_endpoint("GET", "/api/scores?limit=10", "Stock Scores Limited")
        self.test_endpoint("GET", "/api/scores/AAPL", "Single Stock - AAPL")
        self.test_endpoint("GET", "/api/scores/MSFT", "Single Stock - MSFT")
        self.test_endpoint("GET", "/api/scores/INVALID", "Invalid Stock Symbol", 404)
        print()

        # Sector endpoints
        print("🏭 SECTOR ENDPOINTS")
        print("-"*100)
        self.test_endpoint("GET", "/api/sectors", "All Sectors")
        self.test_endpoint("GET", "/api/sectors/Technology", "Single Sector - Technology")
        self.test_endpoint("GET", "/api/sectors/Healthcare", "Single Sector - Healthcare")
        print()

        # Dashboard endpoints
        print("📈 DASHBOARD ENDPOINTS")
        print("-"*100)
        self.test_endpoint("GET", "/api/dashboard", "Dashboard Summary")
        self.test_endpoint("GET", "/api/dashboard/top-movers", "Top Movers")
        print()

        # Analysis endpoints
        print("🔍 ANALYSIS ENDPOINTS")
        print("-"*100)
        self.test_endpoint("GET", "/api/analysis/correlations", "Correlations")
        self.test_endpoint("GET", "/api/analysis/sector-performance", "Sector Performance")
        print()

        # Print summary
        print("\n" + "="*100)
        print(f"TEST RESULTS: {self.passed} passed, {self.failed} failed")
        print("="*100 + "\n")

        return self.results

    def analyze_failures(self):
        """Analyze failed tests"""
        failures = [r for r in self.results if not r.get('success', False)]

        if not failures:
            print("✅ All tests passed!\n")
            return

        print("\n" + "="*100)
        print("FAILED ENDPOINTS - ANALYSIS")
        print("="*100 + "\n")

        for failure in failures:
            print(f"❌ {failure['method']} {failure['endpoint']}")
            print(f"   Expected: {failure['expected']}, Got: {failure['status']}")
            if failure['data']:
                print(f"   Response: {json.dumps(failure['data'], indent=2)[:200]}")
            print()

if __name__ == "__main__":
    # Check if backend is running
    try:
        requests.get(f"{BASE_URL}/health", timeout=2)
    except:
        print(f"❌ Backend not responding at {BASE_URL}")
        print("Please start the backend with: npm start")
        exit(1)

    # Run tests
    tester = APITester(BASE_URL)
    tester.run_all_tests()
    tester.analyze_failures()
