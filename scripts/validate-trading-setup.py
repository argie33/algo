#!/usr/bin/env python3
"""Validate complete trading system setup before deploying to AWS."""

import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_alpaca_credentials():
    """Validate Alpaca API credentials are configured."""
    print("\n[1/5] Checking Alpaca API Credentials...")

    key = os.getenv('APCA_API_KEY_ID')
    secret = os.getenv('APCA_API_SECRET_KEY')

    if not key or not secret:
        print("  [FAIL] CRITICAL: Alpaca credentials not set")
        print("    Required environment variables missing:")
        if not key:
            print("      - APCA_API_KEY_ID")
        if not secret:
            print("      - APCA_API_SECRET_KEY")
        print("\n    Fix: Run scripts/setup-alpaca-credentials.sh")
        return False

    if len(key) < 10:
        print("  [FAIL] API Key ID appears invalid (too short)")
        return False

    print("  [OK] Alpaca credentials configured")
    print(f"    Key ID: {key[:20]}...")
    return True

def check_database_connection():
    """Validate database connectivity."""
    print("\n[2/5] Checking Database Connection...")

    try:
        from utils.db import DatabaseContext
        with DatabaseContext('read') as cur:
            cur.execute("SELECT version()")
            result = cur.fetchone()
            if result:
                print("  [OK] Database connected")
                return True
    except Exception as e:
        print(f"  [FAIL] Database connection failed: {e}")
        return False

def check_entry_date_fixed():
    """Validate entry_date backfill is complete."""
    print("\n[3/5] Checking Trade Entry Dates...")

    try:
        from utils.db import DatabaseContext
        with DatabaseContext('read') as cur:
            cur.execute("SELECT COUNT(*) as count FROM algo_trades WHERE entry_date IS NULL")
            result = cur.fetchone()
            null_count = result[0] if isinstance(result, tuple) else result.get('count', 0)

            if null_count > 0:
                print(f"  [FAIL] Found {null_count} trades with NULL entry_date")
                print("    Run backfill via scripts/validate-trading-setup.py")
                return False

            print("  [OK] All trade entry dates backfilled")
            return True
    except Exception as e:
        print(f"  [FAIL] Entry date check failed: {e}")
        return False

def check_growth_scores():
    """Validate growth scores are loading."""
    print("\n[4/5] Checking Growth Scores...")

    try:
        from utils.db import DatabaseContext
        with DatabaseContext('read') as cur:
            cur.execute("SELECT COUNT(*) as count FROM stock_scores WHERE growth_score IS NOT NULL")
            result = cur.fetchone()
            count = result[0] if isinstance(result, tuple) else result.get('count', 0)

            if count == 0:
                print("  [FAIL] No growth scores found in database")
                print("    Ensure data loaders have completed")
                return False

            print(f"  [OK] Growth scores loaded ({count} stocks)")
            return True
    except Exception as e:
        print(f"  [FAIL] Growth score check failed: {e}")
        return False

def check_orchestrator_config():
    """Validate orchestrator configuration."""
    print("\n[5/5] Checking Orchestrator Configuration...")

    try:
        from config import Config
        config = Config()

        execution_mode = config.get('execution_mode', '')
        if not execution_mode:
            print("  [FAIL] execution_mode not configured")
            print("    Set in algo_config table: execution_mode = 'paper' or 'live'")
            return False

        if execution_mode not in ('paper', 'live', 'auto'):
            print(f"  [FAIL] Invalid execution_mode: {execution_mode}")
            return False

        print(f"  [OK] Orchestrator configured for {execution_mode} mode")
        return True
    except Exception as e:
        print(f"  [FAIL] Orchestrator config check failed: {e}")
        return False

def main():
    print("=" * 60)
    print("ALGO TRADING SYSTEM - SETUP VALIDATION")
    print("=" * 60)

    checks = [
        check_alpaca_credentials,
        check_database_connection,
        check_entry_date_fixed,
        check_growth_scores,
        check_orchestrator_config,
    ]

    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"  [FAIL] Check failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"SUMMARY: {passed}/{total} checks passed")
    print("=" * 60)

    if passed == total:
        print("\n[OK] All checks passed! System is ready to deploy.")
        print("\nNext steps:")
        print("1. Deploy to AWS: git push main (triggers GitHub Actions)")
        print("2. Run orchestrator: aws lambda invoke --function-name algo-orchestrator response.json")
        print("3. Monitor trades: python -m dashboard -w")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} check(s) failed. Fix issues above before deploying.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
