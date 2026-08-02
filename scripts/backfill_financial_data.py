#!/usr/bin/env python3
"""Backfill historical financial data from SEC EDGAR.

This script runs all financial statement loaders with BACKFILL_DAYS set to fetch
historical data (2+ years) to populate NULL columns from before 2026-05-22.

Run: python scripts/backfill_financial_data.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Financial statement loader configs - order matters!
BACKFILL_CONFIGS = [
    # Income statements first (dependencies)
    ("income", "annual"),
    ("income", "quarterly"),
    # Balance sheets
    ("balance", "annual"),
    ("balance", "quarterly"),
    # Cash flow
    ("cashflow", "annual"),
    ("cashflow", "quarterly"),
]

# Backfill depth: 730 days = ~2 years of historical data
BACKFILL_DAYS = "730"

# Timeout per loader: 30 minutes
LOADER_TIMEOUT = 1800

def run_backfill(statement_type: str, period: str) -> bool:
    """Run a single financial statement loader with backfill enabled.

    Returns:
        True if successful, False if failed/timeout
    """
    print(f"\n{'=' * 80}")
    print(f"BACKFILLING: {statement_type} {period} (depth: {BACKFILL_DAYS} days)")
    print(f"{'=' * 80}")

    env = os.environ.copy()
    env["LOADER_STATEMENT_TYPE"] = statement_type
    env["LOADER_PERIOD"] = period
    env["BACKFILL_DAYS"] = BACKFILL_DAYS

    start_time = datetime.now()

    try:
        # Run loader as subprocess
        result = subprocess.run(
            ["python", "loaders/load_financial_statements.py"],
            cwd=str(Path(__file__).parent.parent),
            env=env,
            timeout=LOADER_TIMEOUT,
            capture_output=False,  # Show live output
            text=True,
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        if result.returncode == 0:
            print(f"\n[OK] {statement_type} {period}: completed in {elapsed:.1f}s")
            return True
        else:
            print(f"\n[FAILED] {statement_type} {period}: exit code {result.returncode} after {elapsed:.1f}s")
            return False

    except subprocess.TimeoutExpired:
        print(f"\n[TIMEOUT] {statement_type} {period}: exceeded {LOADER_TIMEOUT}s")
        return False
    except Exception as e:
        print(f"\n[ERROR] {statement_type} {period}: {type(e).__name__}: {e}")
        return False

def main():
    """Run all financial statement loaders with backfill."""
    print(f"FINANCIAL DATA BACKFILL")
    print(f"{'=' * 80}")
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"Backfill depth: {BACKFILL_DAYS} days (~2 years)")
    print(f"Target columns:")
    print(f"  - amortization_expense: 71.8% NULL -> target <20%")
    print(f"  - inventory: 65.8% NULL -> target <25%")
    print(f"  - goodwill: 57.7% NULL -> target <30%")
    print(f"  - accounts_receivable: 59.4% NULL -> target <20%")
    print(f"  - capex: 34.8% NULL -> target <15%")
    print(f"  - depreciation_expense: 45.6% NULL -> target <20%")
    print(f"  - cash_and_equivalents: 26.8% NULL -> target <10%")
    print(f"  - diluted_eps: 20.1% NULL -> target <5%")
    print(f"\nThis will take 30-120 minutes depending on SEC API rate limits.")
    print(f"Monitor progress with: python scripts/audit_data_completeness.py")

    results = {}
    total_start = datetime.now()

    # Run each backfill config
    for statement_type, period in BACKFILL_CONFIGS:
        key = f"{statement_type}_{period}"
        print(f"\n[{len(results)+1}/{len(BACKFILL_CONFIGS)}] Running backfill...")

        success = run_backfill(statement_type, period)
        results[key] = success

        if not success:
            print(f"\n[WARNING] Backfill failed for {key}. Continuing with next...")

        # Brief pause between loaders to avoid overwhelming RDS
        time.sleep(5)

    # Summary
    total_elapsed = (datetime.now() - total_start).total_seconds()
    successful = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    print(f"\n\n{'=' * 80}")
    print(f"BACKFILL COMPLETE")
    print(f"{'=' * 80}")
    print(f"Total time: {total_elapsed/60:.1f} minutes")
    print(f"Successful: {successful}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")

    if failed > 0:
        print(f"\nFailed loaders:")
        for key, success in results.items():
            if not success:
                print(f"  - {key}")

    print(f"\nNext steps:")
    print(f"1. Run: python scripts/audit_data_completeness.py")
    print(f"2. Check NULL % improvements")
    print(f"3. If any column still >50% NULL, investigate if data exists in SEC")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
