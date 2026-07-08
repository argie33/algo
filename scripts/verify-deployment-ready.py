#!/usr/bin/env python3
"""
Pre-Deployment Verification
Verifies that the system is 100% ready before deploying to AWS
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

def main():
    print("=" * 70)
    print("PRE-DEPLOYMENT VERIFICATION")
    print("=" * 70)

    all_pass = True

    # Test 1: Database connectivity
    print("\n[1] Database Connectivity")
    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            cur.execute("SELECT COUNT(*) FROM stock_scores")
            count = cur.fetchone()[0]
        print(f"    [PASS] Database connected ({count} stock scores)")
    except Exception as e:
        print(f"    [FAIL] {e}")
        all_pass = False

    # Test 2: Critical tables exist
    print("\n[2] Database Schema")
    try:
        from utils.db.context import DatabaseContext
        required_tables = {
            'stock_scores': 10000,
            'growth_metrics': 4000,
            'quality_metrics': 4000,
            'algo_positions': 0,  # Can be 0
            'algo_trades': 50,
            'price_daily': 1000000,
            'algo_portfolio_snapshots': 0,  # Will be created
        }

        with DatabaseContext("read") as cur:
            for table, min_rows in required_tables.items():
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                if count >= min_rows:
                    print(f"    [PASS] {table}: {count} rows")
                else:
                    print(f"    [WARN] {table}: {count} rows (expected {min_rows}+)")
                    if min_rows > 0:
                        all_pass = False
    except Exception as e:
        print(f"    [FAIL] {e}")
        all_pass = False

    # Test 3: Credential manager works
    print("\n[3] Credential Manager")
    try:
        import os
        os.environ["APCA_API_KEY_ID"] = "TEST_KEY"
        os.environ["APCA_API_SECRET_KEY"] = "TEST_SECRET"

        from config.credential_manager import get_credential_manager
        mgr = get_credential_manager()
        mgr._cache.clear()

        creds = mgr.get_alpaca_credentials()
        if creds.get("key") == "TEST_KEY" and creds.get("secret") == "TEST_SECRET":
            print("    [PASS] Credential manager loads from env vars")
        else:
            print("    [FAIL] Credential manager not loading correctly")
            all_pass = False
    except Exception as e:
        print(f"    [FAIL] {e}")
        all_pass = False

    # Test 4: All critical modules importable
    print("\n[4] Module Imports")
    modules = {
        'Credential Manager': 'config.credential_manager',
        'Phase 1': 'algo.orchestrator.phase1_data_freshness',
        'Phase 7': 'algo.orchestrator.phase7_signal_generation',
        'Stock Scores Loader': 'loaders.load_stock_scores',
        'Alpaca Sync': 'algo.infrastructure.alpaca_sync_manager',
    }

    for name, module in modules.items():
        try:
            __import__(module)
            print(f"    [PASS] {name}")
        except Exception as e:
            print(f"    [FAIL] {name}: {e}")
            all_pass = False

    # Test 5: API endpoints exist
    print("\n[5] API Endpoints")
    api_files = [
        ('lambda/api/routes/scores.py', '/api/scores'),
        ('lambda/api/routes/positions.py', '/api/positions'),
        ('lambda/api/routes/portfolio.py', '/api/portfolio'),
    ]

    for filepath, endpoint in api_files:
        if os.path.exists(filepath):
            print(f"    [PASS] {endpoint}")
        else:
            print(f"    [FAIL] {endpoint} not found at {filepath}")
            all_pass = False

    # Test 6: Terraform configuration
    print("\n[6] Infrastructure as Code")
    terraform_files = [
        ('terraform/modules/secrets/main.tf', 'Secrets Manager'),
        ('terraform/modules/iam/main.tf', 'IAM Policies'),
        ('terraform/terraform.tfvars', 'Terraform Vars'),
    ]

    for filepath, name in terraform_files:
        if os.path.exists(filepath):
            print(f"    [PASS] {name}")
        else:
            print(f"    [FAIL] {name} not found at {filepath}")
            all_pass = False

    # Test 7: GitHub Actions workflows
    print("\n[7] GitHub Actions Workflows")
    workflow_files = [
        ('.github/workflows/deploy-all-infrastructure.yml', 'Main Deploy'),
        ('.github/workflows/ci.yml', 'CI Tests'),
    ]

    for filepath, name in workflow_files:
        if os.path.exists(filepath):
            print(f"    [PASS] {name}")
        else:
            print(f"    [FAIL] {name} not found at {filepath}")
            all_pass = False

    # Test 8: Data freshness
    print("\n[8] Data Freshness")
    try:
        from utils.db.context import DatabaseContext
        from datetime import datetime, timedelta

        with DatabaseContext("read") as cur:
            # Check price data
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_price = cur.fetchone()[0]

            # Check metrics
            cur.execute("SELECT MAX(updated_at) FROM growth_metrics")
            max_metrics = cur.fetchone()[0]

            now = datetime.utcnow()
            price_age = (now - max_price).days if max_price else None
            metrics_age = (now - max_metrics).days if max_metrics else None

            if price_age is not None and price_age <= 7:
                print(f"    [PASS] Price data fresh ({price_age} days old)")
            else:
                print(f"    [WARN] Price data potentially stale ({price_age} days)")

            if metrics_age is not None and metrics_age <= 7:
                print(f"    [PASS] Metrics fresh ({metrics_age} days old)")
            else:
                print(f"    [WARN] Metrics potentially stale ({metrics_age} days)")
    except Exception as e:
        print(f"    [FAIL] {e}")
        all_pass = False

    # Final summary
    print("\n" + "=" * 70)
    if all_pass:
        print("STATUS: READY FOR DEPLOYMENT")
        print("=" * 70)
        print("\nAll systems verified. You can now:")
        print("  1. Run: python scripts/deploy-system.py")
        print("     OR: ./scripts/deploy-system.sh (Linux/Mac)")
        print("     OR: .\\scripts\\Deploy-System.ps1 (Windows)")
        print("\n  2. Provide your Alpaca credentials")
        print("\n  3. System will deploy automatically to AWS")
        return 0
    else:
        print("STATUS: VERIFICATION FAILED")
        print("=" * 70)
        print("\nFix the failures above before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
