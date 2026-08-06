#!/usr/bin/env python3
"""Complete data refresh pipeline: prices → technical → scores

Runs the full data loading sequence to ensure all factors are current:
1. Reload prices with adj_close
2. Recompute technical indicators using fresh prices
3. Recompute stock scores using fresh technicals + metrics

Usage:
    python scripts/complete_data_refresh.py

This is safe to run anytime and will update all downstream data correctly.
"""

import subprocess
import sys
import time
from pathlib import Path

def run_loader(loader_name: str, timeout: int = 3600) -> bool:
    """Run a loader and report success/failure."""
    print(f"\n{'='*80}")
    print(f"STEP: Loading {loader_name}")
    print(f"{'='*80}")

    result = subprocess.run(
        [sys.executable, "scripts/run_loader.py", loader_name],
        cwd=Path(__file__).parent.parent,
        timeout=timeout,
    )

    if result.returncode == 0:
        print(f"✓ {loader_name} COMPLETE")
        return True
    else:
        print(f"✗ {loader_name} FAILED (exit code {result.returncode})")
        return False

def main():
    print("="*80)
    print("COMPLETE DATA REFRESH: All Factors Updated")
    print("="*80)

    start_time = time.time()
    loaders = [
        ("prices", 3600),          # Reload prices with adj_close
        ("technical", 1800),       # Recompute technicals (SMA, RSI, ROC, etc)
        ("scores", 1800),          # Recompute stock scores
    ]

    failed = []
    for loader_name, timeout in loaders:
        try:
            if not run_loader(loader_name, timeout=timeout):
                failed.append(loader_name)
        except subprocess.TimeoutExpired:
            print(f"✗ {loader_name} TIMED OUT (>{timeout}s)")
            failed.append(loader_name)
        except Exception as e:
            print(f"✗ {loader_name} ERROR: {e}")
            failed.append(loader_name)

        # Small delay between loaders
        time.sleep(2)

    elapsed = time.time() - start_time

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Elapsed time: {elapsed/60:.1f} minutes")

    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        return 1
    else:
        print("\n✓ ALL LOADERS COMPLETE - Data refresh successful!")
        print("\nNext steps:")
        print("  1. Verify adj_close populated: python -c \"from utils.db import DatabaseContext; ...")
        print("  2. Start dashboard: python start_dashboard_dev.py")
        print("  3. Check dashboard for signals")
        return 0

if __name__ == "__main__":
    sys.exit(main())
