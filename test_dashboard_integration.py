#!/usr/bin/env python3
"""Dashboard Integration Test - Verify API responses match schema and display data correctly"""
import sys
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_dashboard_endpoints():
    """Test all dashboard API endpoints against expected schemas."""
    logger.info("=" * 80)
    logger.info("DASHBOARD INTEGRATION TEST")
    logger.info("=" * 80)

    try:
        import requests
        import json
    except ImportError:
        logger.error("requests library required: pip install requests")
        return False

    # API endpoints to test
    endpoints = [
        ("/api/portfolio", "Portfolio summary data"),
        ("/api/positions", "Open positions"),
        ("/api/signals", "Generated trading signals"),
        ("/api/metrics", "Portfolio metrics"),
        ("/api/risk-dashboard", "Risk dashboard data"),
    ]

    base_url = "http://localhost:3000"
    results = []

    for endpoint, description in endpoints:
        url = f"{base_url}{endpoint}"
        logger.info(f"\nTesting: {description}")
        logger.info(f"  URL: {url}")

        try:
            response = requests.get(url, timeout=5)
            logger.info(f"  Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                # Validate response structure
                if "data" in data:
                    logger.info(f"  ✓ Response has 'data' field")
                    logger.info(f"  ✓ Data keys: {list(data['data'].keys())[:5]}")
                    results.append((endpoint, True, "OK"))
                else:
                    logger.warning(f"  ✗ Response missing 'data' field")
                    logger.warning(f"  Response structure: {list(data.keys())}")
                    results.append((endpoint, False, "Invalid schema"))
            else:
                logger.warning(f"  ✗ HTTP {response.status_code}")
                results.append((endpoint, False, f"HTTP {response.status_code}"))

        except requests.exceptions.ConnectionError:
            logger.warning(f"  ✗ Connection refused (dashboard not running)")
            results.append((endpoint, False, "Dashboard offline"))
        except Exception as e:
            logger.error(f"  ✗ Error: {e}")
            results.append((endpoint, False, str(e)))

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("DASHBOARD TEST SUMMARY")
    logger.info("=" * 80)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for endpoint, success, msg in results:
        status = "✓" if success else "✗"
        logger.info(f"  {status} {endpoint:30s} {msg}")

    logger.info(f"\nResult: {passed}/{total} endpoints responding correctly")

    if passed == total:
        logger.info("✓ Dashboard integration test PASSED")
        return True
    else:
        logger.warning("✗ Dashboard integration test FAILED")
        return False

if __name__ == "__main__":
    success = test_dashboard_endpoints()
    sys.exit(0 if success else 1)
