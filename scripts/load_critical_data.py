#!/usr/bin/env python3
"""Load critical data for dashboard display.

This script loads the minimum required data to:
1. Show portfolio/positions/trades in the dashboard
2. Run the orchestrator successfully
3. Display data in all dashboard panels

Run this BEFORE starting the dashboard or orchestrator.
"""

import subprocess
import sys
import time
import os
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

def run_loader(script: str, description: str, args: list[str] | None = None) -> bool:
    """Run a loader script and return success/failure."""
    args = args or []
    cmd = [sys.executable, str(repo_root / script)] + args

    print(f"\n{'='*70}")
    print(f"[{time.strftime('%H:%M:%S')}] {description}")
    print(f"{'='*70}")
    print(f"Running: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(cmd, timeout=300, check=False)
        if result.returncode == 0:
            print(f"✓ {description} - SUCCESS")
            return True
        else:
            print(f"✗ {description} - FAILED (exit code {result.returncode})")
            return False
    except subprocess.TimeoutExpired:
        print(f"✗ {description} - TIMEOUT (>5 min)")
        return False
    except Exception as e:
        print(f"✗ {description} - ERROR: {e}")
        return False

def main() -> int:
    """Load critical data."""
    print("\n" + "="*70)
    print("CRITICAL DATA LOADER")
    print("="*70)
    print("\nLoading minimum data for dashboard display and orchestrator execution")
    print(f"Starting at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = {}

    # 1. Load prices (most critical - needed by orchestrator for position evaluation)
    # Load just SPY, QQQ, and a few top symbols for speed
    results['prices'] = run_loader(
        'loaders/load_prices.py',
        'Loading prices (SPY, QQQ)',
        ['--symbols', 'SPY,QQQ,TQQQ,SQQQ']
    )

    # 2. Load market health (needed by orchestrator Phase 1 data freshness check)
    results['market_health'] = run_loader(
        'loaders/load_market_health_daily.py',
        'Loading market health indicators'
    )

    # 3. Load stock scores (needed by orchestrator signal evaluation)
    results['stock_scores'] = run_loader(
        'loaders/load_stock_scores.py',
        'Loading stock scores'
    )

    # 4. Load technical data (needed by orchest Phase 4 momentum/trend analysis)
    results['technical_data'] = run_loader(
        'loaders/load_technical_data_daily.py',
        'Loading technical indicators'
    )

    # 5. Load market sentiment
    results['sentiment'] = run_loader(
        'loaders/load_market_sentiment.py',
        'Loading market sentiment'
    )

    # Print summary
    print("\n" + "="*70)
    print("LOADING SUMMARY")
    print("="*70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for script, success in results.items():
        status = "✓" if success else "✗"
        print(f"{status} {script}")

    print(f"\n{passed}/{total} loaders completed successfully")

    if passed == total:
        print("\n✓ All critical data loaded. Dashboard should now display data.")
        return 0
    else:
        print(f"\n⚠ {total - passed} loader(s) failed. Dashboard may show incomplete data.")
        print("Check error messages above for details.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
