#!/usr/bin/env python3
"""Comprehensive system health check - identifies what's working and what's not.

Usage:
  python3 scripts/system_health_check.py
  python3 scripts/system_health_check.py --verbose

This diagnoses the system state and points to specific issues.
"""

import sys
import socket
import psycopg2
import requests
import argparse
import logging
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def check_database():
    """Check PostgreSQL database connectivity."""
    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        # Check data tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cur.fetchall()]

        # Check key data freshness
        cur.execute("""
            SELECT 'price_daily' as table_name, MAX(date) as latest_date
            FROM price_daily
            UNION ALL
            SELECT 'technical_data_daily', MAX(date) FROM technical_data_daily
            UNION ALL
            SELECT 'buy_sell_daily', MAX(date) FROM buy_sell_daily
            UNION ALL
            SELECT 'stock_scores', MAX(updated_at) FROM stock_scores
        """)
        freshness = {row[0]: row[1] for row in cur.fetchall()}

        cur.close()
        conn.close()

        logger.info(f"\n✓ Database: Connected")
        logger.info(f"  Tables: {len(tables)} total")
        for table, latest in freshness.items():
            if latest:
                age_days = (date.today() - latest.date()).days if hasattr(latest, 'date') else (datetime.now() - latest).days
                logger.info(f"  {table:25s} latest: {latest} ({age_days}d old)")
            else:
                logger.info(f"  {table:25s} EMPTY")

        return True
    except Exception as e:
        logger.error(f"✗ Database: Failed - {e}")
        return False


def check_dev_server():
    """Check if dev_server is running on :3001."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 3001))
        sock.close()

        if result == 0:
            logger.info(f"✓ Dev Server: Running on localhost:3001")
            return True
        else:
            logger.error(f"✗ Dev Server: NOT running on localhost:3001")
            logger.info(f"  Start with: python3 api-pkg/dev_server.py")
            return False
    except Exception as e:
        logger.error(f"✗ Dev Server: Check failed - {e}")
        return False


def check_api_endpoints():
    """Check key API endpoints."""
    base_url = "http://localhost:3001"
    endpoints = {
        "/health": "System health",
        "/api/algo/portfolio": "Portfolio data",
        "/api/algo/positions": "Open positions",
        "/api/algo/data-status": "Data freshness status",
    }

    results = {}
    for endpoint, desc in endpoints.items():
        try:
            headers = {"Authorization": "Bearer dev-admin"}
            response = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=5)

            if response.status_code == 200:
                logger.info(f"  ✓ {endpoint:35s} OK")
                results[endpoint] = True
            else:
                logger.warning(f"  ✗ {endpoint:35s} {response.status_code}")
                results[endpoint] = False
        except requests.exceptions.ConnectionError:
            logger.error(f"  ✗ {endpoint:35s} Connection refused")
            results[endpoint] = False
        except Exception as e:
            logger.error(f"  ✗ {endpoint:35s} {type(e).__name__}: {str(e)[:50]}")
            results[endpoint] = False

    return all(results.values())


def check_dashboard():
    """Check dashboard startup."""
    try:
        # Ensure dashboard is on sys.path
        import os
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        # Try to import dashboard modules
        from dashboard.api_data_layer import _get_api_base_url
        from dashboard.fetchers_config import fetch_health

        url = _get_api_base_url()
        logger.info(f"✓ Dashboard: Modules load OK")
        logger.info(f"  API URL: {url}")

        # Try a health check fetch
        try:
            health = fetch_health(None)
            if "_error" not in health:
                logger.info(f"  Health fetch: OK")
                return True
            else:
                logger.warning(f"  Health fetch error: {health.get('_error', 'unknown')}")
                return False
        except Exception as e:
            logger.warning(f"  Health fetch failed: {e}")
            return False

    except Exception as e:
        logger.error(f"✗ Dashboard: Import failed - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="System health check")
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("\n" + "="*70)
    logger.info("SYSTEM HEALTH CHECK")
    logger.info("="*70)

    results = {}

    logger.info("\n[1] Database Connection")
    results['database'] = check_database()

    logger.info("\n[2] Dev Server")
    results['dev_server'] = check_dev_server()

    if results['dev_server']:
        logger.info("\n[3] API Endpoints")
        try:
            results['api'] = check_api_endpoints()
        except Exception as e:
            logger.error(f"API check failed: {e}")
            results['api'] = False

        logger.info("\n[4] Dashboard")
        try:
            results['dashboard'] = check_dashboard()
        except Exception as e:
            logger.error(f"Dashboard check failed: {e}")
            results['dashboard'] = False

    logger.info("\n" + "="*70)
    logger.info("SUMMARY")
    logger.info("="*70)

    for check, status in results.items():
        status_str = "OK" if status else "FAILED"
        logger.info(f"  {check:20s}: {status_str}")

    all_ok = all(results.values())

    if all_ok:
        logger.info("\n✓ All systems operational!")
        logger.info("\nTo run dashboard:")
        logger.info("  python3 dashboard/dashboard.py --local")
        logger.info("\nTo run loaders:")
        logger.info("  python3 scripts/run_loader.py prices")
        return 0
    else:
        logger.info("\n✗ Some systems not operational. Fix issues above and retry.")
        if not results.get('dev_server'):
            logger.info("\nFirst step: Start dev server in another terminal")
            logger.info("  python3 api-pkg/dev_server.py")
        return 1


if __name__ == '__main__':
    sys.exit(main())
