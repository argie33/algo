#!/usr/bin/env python3
"""End-to-end system test to verify all components work together."""

import logging
import subprocess
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def test_dev_server():
    """Start dev server and test API endpoints."""
    logger.info("\n=== Testing Dev Server ===")

    # Start dev server
    proc = subprocess.Popen(
        ["python3", "lambda/api/dev_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(4)  # Give server time to start

    endpoints = [
        "/api/algo/portfolio",
        "/api/algo/health",
        "/api/algo/positions",
        "/api/algo/config",
        "/api/algo/dashboard-signals",
        "/api/algo/scores",
    ]

    failed = []
    for endpoint in endpoints:
        try:
            r = requests.get(
                f"http://localhost:3001{endpoint}", headers={"Authorization": "Bearer dev-admin"}, timeout=5
            )
            if r.status_code == 200:
                data = r.json()
                if "_error" not in str(data):
                    logger.info(f"  ✓ {endpoint}")
                else:
                    logger.error(f"  ✗ {endpoint}: {data.get('_error', 'unknown error')[:100]}")
                    failed.append(endpoint)
            else:
                logger.error(f"  ✗ {endpoint}: HTTP {r.status_code}")
                failed.append(endpoint)
        except Exception as e:
            logger.error(f"  ✗ {endpoint}: {e}")
            failed.append(endpoint)

    proc.terminate()
    proc.wait(timeout=5)

    return len(failed) == 0


def test_database():
    """Test database connectivity and data freshness."""
    logger.info("\n=== Testing Database ===")

    try:
        import psycopg2

        conn = psycopg2.connect(dbname="stocks", user="stocks", host="localhost")
        cur = conn.cursor()

        # Check key tables
        tables = [
            "price_daily",
            "technical_data_daily",
            "stock_scores",
            "algo_positions",
        ]

        all_ok = True
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            if count > 0:
                logger.info(f"  ✓ {table}: {count:,} rows")
            else:
                logger.error(f"  ✗ {table}: EMPTY")
                all_ok = False

        cur.close()
        conn.close()
        return all_ok
    except Exception as e:
        logger.error(f"  ✗ Database error: {e}")
        return False


def test_loaders():
    """Test that loaders can run without errors."""
    logger.info("\n=== Testing Loaders (Quick Validation) ===")

    try:
        # Test price fetcher
        from loaders.price_fetcher import PriceFetcher

        fetcher = PriceFetcher()
        logger.info("  ✓ PriceFetcher initialized")

        # Test database context
        from utils.db.context import DatabaseContext

        with DatabaseContext("read") as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        logger.info("  ✓ DatabaseContext working")

        return True
    except Exception as e:
        logger.error(f"  ✗ Loader error: {e}")
        return False


def test_dashboard_fetchers():
    """Test that dashboard fetchers load correctly."""
    logger.info("\n=== Testing Dashboard Fetchers ===")

    # Start dev server first
    proc = subprocess.Popen(
        ["python3", "lambda/api/dev_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(4)

    try:
        import sys

        sys.path.insert(0, "dashboard")
        from fetchers import FETCHERS

        # Test a few critical fetchers
        critical = ["run", "cfg", "mkt", "port", "health"]
        failed = []

        for key in critical:
            if key not in FETCHERS:
                logger.error(f"  ✗ {key}: NOT FOUND")
                failed.append(key)
                continue

            try:
                result = FETCHERS[key](None)
                if isinstance(result, dict) and "_error" in result:
                    logger.error(f"  ✗ {key}: {result['_error'][:80]}")
                    failed.append(key)
                else:
                    logger.info(f"  ✓ {key}")
            except Exception as e:
                logger.error(f"  ✗ {key}: {str(e)[:80]}")
                failed.append(key)

        success = len(failed) == 0
    except Exception as e:
        logger.error(f"  ✗ Fetcher loading error: {e}")
        success = False
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()

    return success


def main():
    logger.info("=" * 70)
    logger.info("END-TO-END SYSTEM TEST")
    logger.info("=" * 70)

    results = []

    # Run tests
    results.append(("Database", test_database()))
    results.append(("Dev Server", test_dev_server()))
    results.append(("Loaders", test_loaders()))
    results.append(("Dashboard Fetchers", test_dashboard_fetchers()))

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    logger.info(f"\nPassed: {passed_count}/{total_count}")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
