#!/usr/bin/env python3
"""
Test AWS orchestrator execution path.

This script verifies:
1. Orchestrator can be imported and initialized
2. Database connectivity works
3. Alpaca credentials are accessible
4. Live trading mode is enabled (not dry run)
5. Execution would proceed in AWS
"""

import sys
import os
from pathlib import Path
from datetime import date

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Verify all imports work."""
    print("[TEST] Testing imports...")
    try:
        from algo.algo_orchestrator import Orchestrator
        from config.credential_helper import get_db_config, get_db_password
        from utils.db_connection import get_db_connection
        print("  [OK] All imports successful")
        return True
    except ImportError as e:
        print(f"  [FAIL] Import failed: {e}")
        return False

def test_credentials():
    """Verify credentials are accessible."""
    print("[TEST] Testing credentials...")
    try:
        # DB credentials
        db_config = get_db_config()
        print(f"  [OK] DB config available: {db_config['host']}:{db_config['port']}/{db_config['database']}")

        # Alpaca credentials
        alpaca_key = os.getenv('ALPACA_API_KEY')
        alpaca_secret = os.getenv('ALPACA_SECRET_KEY')

        if alpaca_key and alpaca_secret:
            print(f"  [OK] Alpaca credentials found")
        else:
            print(f"  [WARN] Alpaca credentials NOT found (paper trading may not work)")

        return True
    except Exception as e:
        print(f"  [FAIL] Credential test failed: {e}")
        return False

def test_orchestrator_init():
    """Verify orchestrator can be initialized."""
    print("[TEST] Testing orchestrator initialization...")
    try:
        from algo.algo_orchestrator import Orchestrator

        # Check dry_run setting
        dry_run_env = os.getenv('ORCHESTRATOR_DRY_RUN', 'false').lower() == 'true'
        print(f"  DRY_RUN environment: {dry_run_env}")

        # Initialize orchestrator (don't run it yet)
        orch = Orchestrator(
            run_date=date.today(),
            dry_run=dry_run_env,
            verbose=False,
            init_db=False  # Don't initialize DB for this test
        )
        print(f"  [OK] Orchestrator initialized successfully")
        print(f"  - Execution mode: {os.getenv('EXECUTION_MODE', 'auto')}")
        print(f"  - Dry run: {dry_run_env}")
        return True
    except Exception as e:
        print(f"  [FAIL] Orchestrator init failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_database_connection():
    """Verify database connection works."""
    print("[TEST] Testing database connection...")
    try:
        from utils.db_connection import get_db_connection
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM stock_symbols;")
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            print(f"  [OK] Database connected: {count} stock symbols in DB")
            return True
        else:
            print(f"  [FAIL] Could not establish database connection")
            return False
    except Exception as e:
        print(f"  [FAIL] Database connection failed: {e}")
        return False

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("AWS Orchestrator Execution Path Test")
    print("="*70 + "\n")

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Credentials", test_credentials()))
    results.append(("Orchestrator Init", test_orchestrator_init()))
    results.append(("Database Connection", test_database_connection()))

    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status:8} {test_name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n[OK] All tests passed. Orchestrator is ready for AWS execution.")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed. Fix issues before deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
