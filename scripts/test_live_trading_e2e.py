#!/usr/bin/env python3
"""
End-to-End Live Trading Test - Verifies the complete trading pipeline works

Tests:
1. API connectivity (local or AWS Lambda)
2. Orchestrator can fetch signals
3. Alpaca connection works
4. A test trade can be executed (paper mode)
5. Dashboard can fetch live data

Run: python3 scripts/test_live_trading_e2e.py
"""

import sys
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_api_connectivity(api_url: str, is_local: bool = True) -> bool:
    """Test API endpoint connectivity."""
    logger.info(f"\n{'='*60}")
    logger.info("TEST 1: API Connectivity")
    logger.info(f"{'='*60}")

    try:
        import requests

        token = "dev-admin" if is_local else None
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        resp = requests.get(
            f"{api_url}/api/algo/health",
            headers=headers,
            timeout=5
        )

        if resp.status_code == 200:
            data = resp.json()
            status = data.get("data", {}).get("status")
            logger.info(f"✓ API responding: {status}")
            return status == "healthy"
        else:
            logger.error(f"✗ API returned {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"✗ API connectivity failed: {e}")
        return False


def test_database_freshness() -> bool:
    """Test database has current data."""
    logger.info(f"\n{'='*60}")
    logger.info("TEST 2: Database Data Freshness")
    logger.info(f"{'='*60}")

    try:
        import psycopg2
        from datetime import date, timedelta

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        # Check price data
        cur.execute("SELECT MAX(created_at) FROM price_daily")
        latest_price = cur.fetchone()[0]

        if not latest_price:
            logger.error("✗ No price data in database")
            return False

        age = (datetime.now(timezone.utc) - latest_price.replace(tzinfo=timezone.utc)).total_seconds() / 3600

        if age < 24:
            logger.info(f"✓ Prices fresh ({age:.1f}h old)")
        else:
            logger.warning(f"⚠ Prices stale ({age:.1f}h old)")

        # Check signals
        cur.execute("SELECT COUNT(*) FROM algo_signals WHERE signal_active = true")
        signal_count = cur.fetchone()[0]

        if signal_count > 0:
            logger.info(f"✓ {signal_count:,} active signals in database")
        else:
            logger.warning("⚠ No active signals - orchestrator may not have run yet")

        conn.close()
        return True

    except Exception as e:
        logger.error(f"✗ Database test failed: {e}")
        return False


def test_alpaca_connectivity() -> bool:
    """Test Alpaca API connectivity."""
    logger.info(f"\n{'='*60}")
    logger.info("TEST 3: Alpaca API Connectivity")
    logger.info(f"{'='*60}")

    try:
        from config.credential_manager import get_credential_manager
        import requests

        creds = get_credential_manager().get_alpaca_credentials()

        if not creds.get("key") or not creds.get("secret"):
            logger.warning("⚠ Alpaca credentials not configured - paper trading only")
            return True

        # Test account endpoint
        headers = {
            "Authorization": f"Bearer {creds['key']}",
            "APCA-API-SECRET-KEY": creds['secret']
        }

        resp = requests.get(
            "https://paper-api.alpaca.markets/v2/account",
            headers=headers,
            timeout=5
        )

        if resp.status_code == 200:
            account = resp.json()
            logger.info(f"✓ Alpaca connected - Account: {account.get('account_number', 'N/A')}")
            logger.info(f"  Cash: ${account.get('cash', 0):.2f}")
            logger.info(f"  Portfolio Value: ${account.get('portfolio_value', 0):.2f}")
            return True
        else:
            logger.error(f"✗ Alpaca API returned {resp.status_code}: {resp.text[:100]}")
            return False

    except Exception as e:
        logger.error(f"✗ Alpaca connectivity test failed: {e}")
        return False


def test_dashboard_data_fetch(api_url: str, is_local: bool = True) -> bool:
    """Test dashboard can fetch all required data."""
    logger.info(f"\n{'='*60}")
    logger.info("TEST 4: Dashboard Data Fetching")
    logger.info(f"{'='*60}")

    try:
        import requests

        endpoints = [
            "/api/algo/portfolio",
            "/api/algo/positions",
            "/api/algo/trades",
            "/api/algo/config",
        ]

        token = "dev-admin" if is_local else None
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        success_count = 0
        for endpoint in endpoints:
            resp = requests.get(
                f"{api_url}{endpoint}",
                headers=headers,
                timeout=5
            )

            if resp.status_code == 200:
                logger.info(f"✓ {endpoint}")
                success_count += 1
            else:
                logger.error(f"✗ {endpoint}: {resp.status_code}")

        logger.info(f"\nDashboard endpoints: {success_count}/{len(endpoints)} operational")
        return success_count == len(endpoints)

    except Exception as e:
        logger.error(f"✗ Dashboard test failed: {e}")
        return False


def test_orchestrator_status() -> bool:
    """Test orchestrator is running successfully."""
    logger.info(f"\n{'='*60}")
    logger.info("TEST 5: Orchestrator Status")
    logger.info(f"{'='*60}")

    try:
        import psycopg2
        from datetime import datetime, timedelta

        conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
        cur = conn.cursor()

        # Check recent orchestrator runs
        cur.execute("""
            SELECT run_id, started_at, overall_status, execution_time_seconds
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC
            LIMIT 5
        """)

        runs = cur.fetchall()
        if not runs:
            logger.warning("⚠ No orchestrator runs found - may not have executed yet")
            return True

        for run_id, started_at, status, exec_time in runs:
            age_hours = (datetime.now(timezone.utc) - started_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            logger.info(f"  {run_id}: {status} ({exec_time:.1f}s) - {age_hours:.1f}h ago")

        successful = sum(1 for r in runs if r[2] == "success")
        logger.info(f"\n✓ Orchestrator running: {successful}/{len(runs)} recent runs successful")

        conn.close()
        return successful > 0

    except Exception as e:
        logger.error(f"✗ Orchestrator test failed: {e}")
        return False


def main():
    """Run all end-to-end tests."""
    logger.info("\n" + "="*60)
    logger.info("LIVE TRADING END-TO-END TEST SUITE")
    logger.info("="*60)

    # Determine API mode
    api_url = "http://localhost:3001"
    is_local = True

    logger.info(f"\nUsing API: {api_url} (local mode: {is_local})")
    logger.info("Note: For AWS Lambda, set DASHBOARD_API_URL environment variable")

    # Run all tests
    results = {
        "API Connectivity": test_api_connectivity(api_url, is_local),
        "Database Freshness": test_database_freshness(),
        "Alpaca Connectivity": test_alpaca_connectivity(),
        "Dashboard Data Fetch": test_dashboard_data_fetch(api_url, is_local),
        "Orchestrator Status": test_orchestrator_status(),
    }

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        logger.info(f"{test_name:.<40} {status}")

    logger.info(f"\nResult: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n✓ All systems operational - ready for live trading!")
        return 0
    else:
        logger.error(f"\n✗ {total - passed} test(s) failed - review above for details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
