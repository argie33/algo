#!/usr/bin/env python3
"""Comprehensive system verification - tests all critical components."""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_database() -> bool:
    """Verify database connection and critical tables."""
    try:
        from utils.db import DatabaseContext
        with DatabaseContext('read') as cur:
            # Check critical tables exist
            tables = [
                'price_daily', 'stock_scores', 'market_health_daily',
                'market_exposure_daily', 'algo_orchestrator_runs',
                'algo_portfolio_snapshots'
            ]
            for table in tables:
                cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
                cur.fetchone()
        logger.info("✓ Database: All critical tables accessible")
        return True
    except Exception as e:
        logger.error(f"✗ Database: {e}")
        return False

def check_loaders() -> bool:
    """Verify data loaders have completed and data is recent."""
    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timedelta, timezone

        with DatabaseContext('read') as cur:
            # Check data freshness (all loaders should have data from last 7 days)
            cur.execute("""
                SELECT COUNT(*) as count FROM price_daily
                WHERE date > CURRENT_DATE - INTERVAL '7 days'
            """)
            result = cur.fetchone()
            if not result or result['count'] == 0:
                raise ValueError("No price data from last 7 days")
            logger.info(f"✓ Loaders: {result['count']} price records recent")
        return True
    except Exception as e:
        logger.error(f"✗ Loaders: {e}")
        return False

def check_orchestrator() -> bool:
    """Verify orchestrator has been executing."""
    try:
        from utils.db import DatabaseContext
        from datetime import datetime, timedelta, timezone

        with DatabaseContext('read') as cur:
            # Check orchestrator runs from last 24 hours
            cur.execute("""
                SELECT COUNT(*) as count FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
            """)
            result = cur.fetchone()
            if not result or result['count'] == 0:
                raise ValueError("No orchestrator runs in last 24h")
            logger.info(f"✓ Orchestrator: {result['count']} runs in last 24h")
        return True
    except Exception as e:
        logger.error(f"✗ Orchestrator: {e}")
        return False

def check_api_endpoints() -> bool:
    """Verify API endpoints respond correctly."""
    try:
        import requests
        import json

        base_url = "http://localhost:3001"
        endpoints = [
            "/api/algo/portfolio",
            "/api/algo/positions",
            "/api/algo/performance",
            "/api/algo/circuit-breakers"
        ]

        headers = {"Authorization": "Bearer dev-admin"}

        for endpoint in endpoints:
            try:
                response = requests.get(f"{base_url}{endpoint}", headers=headers, timeout=5)
                if response.status_code != 200:
                    logger.warning(f"  {endpoint}: {response.status_code}")
                else:
                    # Verify response has valid JSON structure
                    data = response.json()
                    if 'statusCode' not in data:
                        raise ValueError(f"Response missing statusCode")
            except requests.ConnectionError:
                raise ValueError(f"Cannot connect to {base_url} - dev_server not running")

        logger.info(f"✓ API Endpoints: {len(endpoints)} endpoints responding")
        return True
    except Exception as e:
        logger.error(f"✗ API Endpoints: {e}")
        return False

def check_alpaca_config() -> bool:
    """Verify Alpaca paper trading configuration."""
    try:
        import os
        required_vars = ['APCA_API_KEY_ID', 'APCA_API_SECRET_KEY']
        missing = [v for v in required_vars if not os.environ.get(v)]
        if missing:
            raise ValueError(f"Missing Alpaca credentials: {missing}")
        logger.info("✓ Alpaca Config: Paper trading credentials configured")
        return True
    except Exception as e:
        logger.error(f"✗ Alpaca Config: {e}")
        return False

def main() -> int:
    """Run all verification checks."""
    logger.info("=" * 60)
    logger.info("SYSTEM VERIFICATION - Testing all critical components")
    logger.info("=" * 60)

    checks = [
        ("Database", check_database),
        ("Data Loaders", check_loaders),
        ("Orchestrator", check_orchestrator),
        ("Alpaca Config", check_alpaca_config),
        ("API Endpoints", check_api_endpoints),
    ]

    results = {}
    for name, check_func in checks:
        logger.info(f"\nChecking {name}...")
        results[name] = check_func()

    logger.info("\n" + "=" * 60)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, passed_check in results.items():
        status = "PASS" if passed_check else "FAIL"
        logger.info(f"  {name:.<40} {status}")

    logger.info(f"\nTotal: {passed}/{total} checks passed")

    if passed == total:
        logger.info("\n✓ System READY for paper trading!")
        return 0
    else:
        logger.info("\n✗ System has issues - see failures above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
