#!/usr/bin/env python3
"""
Full end-to-end pipeline test after fresh data loading.
Verifies data completeness, then runs orchestrator and validates output.
"""
import sys
import subprocess
from datetime import date, timedelta
from utils.db_connection import get_db_connection

def check_data_completeness():
    """Verify critical data tables are loaded and recent."""
    conn = get_db_connection()
    cur = conn.cursor()

    today = date.today()
    yesterday = today - timedelta(days=1)

    print("\n" + "="*70)
    print("DATA COMPLETENESS CHECK")
    print("="*70)

    checks = [
        ("price_daily", f"SELECT COUNT(*) FROM price_daily WHERE date >= '{yesterday}'"),
        ("technical_data_daily", f"SELECT COUNT(*) FROM technical_data_daily WHERE date >= '{yesterday}'"),
        ("buy_sell_daily", f"SELECT COUNT(*) FROM buy_sell_daily WHERE date >= '{yesterday}'"),
        ("stock_symbols", f"SELECT COUNT(*) FROM stock_symbols"),
    ]

    all_ok = True
    for table_name, query in checks:
        try:
            cur.execute(query)
            count = cur.fetchone()[0] or 0
            if count > 0:
                print(f"✅ {table_name}: {count:,} rows")
            else:
                print(f"❌ {table_name}: NO DATA")
                all_ok = False
        except Exception as e:
            print(f"❌ {table_name}: ERROR - {e}")
            all_ok = False

    conn.close()

    if not all_ok:
        print("\n❌ DATA INCOMPLETE - Cannot run orchestrator")
        return False

    print("\n✅ ALL DATA PRESENT - Running orchestrator test")
    return True

def run_orchestrator_test():
    """Run orchestrator in dry-run mode and check for signals."""
    print("\n" + "="*70)
    print("ORCHESTRATOR DRY-RUN TEST")
    print("="*70 + "\n")

    try:
        # Run with DEV_MODE to use existing data
        result = subprocess.run(
            ["python3", "algo/algo_orchestrator.py", "--dry-run"],
            env={
                "DB_HOST": "localhost",
                "DB_PASSWORD": "stocks",
                "DB_USER": "stocks",
                "DEV_MODE": "true",
            },
            capture_output=True,
            text=True,
            timeout=300
        )

        # Parse output for key metrics
        output = result.stdout + result.stderr
        has_phases = "Phase" in output or "phase" in output
        has_signals = "Signal" in output or "signal" in output
        has_error = "ERROR" in output or "error" in output

        print(output)

        print("\n" + "="*70)
        if result.returncode == 0 and not has_error:
            print("✅ ORCHESTRATOR PASSED")
            if has_signals:
                print("✅ SIGNALS GENERATED")
            print("="*70)
            return True
        else:
            print("❌ ORCHESTRATOR FAILED")
            print(f"   Exit code: {result.returncode}")
            print("="*70)
            return False

    except subprocess.TimeoutExpired:
        print("❌ ORCHESTRATOR TIMEOUT (>300s)")
        return False
    except Exception as e:
        print(f"❌ ORCHESTRATOR ERROR: {e}")
        return False

def main():
    print("\n" + "="*70)
    print("FULL PIPELINE VALIDATION")
    print("="*70)

    # Step 1: Check data
    if not check_data_completeness():
        print("\n[FINAL] ❌ FAILED - Data incomplete")
        return 1

    # Step 2: Run orchestrator
    if not run_orchestrator_test():
        print("\n[FINAL] ❌ FAILED - Orchestrator error")
        return 1

    # Step 3: Success
    print("\n" + "="*70)
    print("[FINAL] ✅ FULL PIPELINE WORKING")
    print("="*70 + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
