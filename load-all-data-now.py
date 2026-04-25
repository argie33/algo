#!/usr/bin/env python3
"""
COMPREHENSIVE DATA LOADER
Runs ALL loaders systematically to populate the complete dataset with REAL data only
"""

import subprocess
import sys
import os
import io
import time
from datetime import datetime
from pathlib import Path

# Fix Unicode on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Critical loaders that must run first (they unlock other features)
PRIORITY_LOADERS = [
    ('loaddailycompanydata.py', 'Company Data & Earnings'),
    ('loadfactormetrics.py', 'Factor Metrics (CRITICAL - quality/value/stability)'),
    ('loadbuysellweekly.py', 'Buy/Sell Signals'),
    ('loadstockscores.py', 'Stock Scores Calculation'),
]

# Secondary loaders (add value but not critical)
SECONDARY_LOADERS = [
    ('loadbuyselldaily.py', 'Daily Buy/Sell Signals'),
    ('loadbuysellmonthly.py', 'Monthly Buy/Sell Signals'),
    ('loadecondata.py', 'Economic Data'),
    ('loadetfpricedaily.py', 'ETF Prices Daily'),
    ('loadearningshistory.py', 'Earnings History'),
    ('loadsectorranking.py', 'Sector Rankings') if os.path.exists('loadsectorranking.py') else None,
]

SECONDARY_LOADERS = [x for x in SECONDARY_LOADERS if x is not None]

def run_loader(loader_file, loader_name, is_priority=False):
    """Run a single loader with error handling"""
    print(f"\n{'='*70}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Running: {loader_name}")
    print(f"File: {loader_file}")
    print('='*70)

    try:
        result = subprocess.run(
            [sys.executable, loader_file],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            print(f"[SUCCESS] {loader_name} completed")
            # Show last few lines
            lines = result.stdout.split('\n')
            for line in lines[-10:]:
                if line.strip() and ('rows' in line.lower() or 'complete' in line.lower() or 'saved' in line.lower()):
                    print(f"  {line}")
            return True
        else:
            print(f"[ERROR] {loader_name} failed with exit code {result.returncode}")
            if result.stderr:
                print("STDERR:")
                for line in result.stderr.split('\n')[-15:]:
                    if line.strip():
                        print(f"  {line}")
            if result.stdout:
                print("Last stdout:")
                for line in result.stdout.split('\n')[-10:]:
                    if line.strip():
                        print(f"  {line}")
            return False

    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {loader_name} exceeded 5 minute timeout")
        return False
    except Exception as e:
        print(f"[EXCEPTION] {loader_name}: {str(e)}")
        return False

def main():
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                  COMPREHENSIVE DATA LOADER                         ║
║              Loading REAL data - No mocks, no fallbacks            ║
╚════════════════════════════════════════════════════════════════════╝
    """)

    results = {}
    start_time = time.time()

    # Priority loaders first
    print("\n[PHASE 1] PRIORITY LOADERS (must complete for full functionality)")
    for loader_file, loader_name in PRIORITY_LOADERS:
        if os.path.exists(loader_file):
            success = run_loader(loader_file, loader_name, is_priority=True)
            results[loader_name] = 'SUCCESS' if success else 'FAILED'
        else:
            print(f"[SKIP] {loader_name} - file not found")
            results[loader_name] = 'SKIPPED'

    # Secondary loaders
    print("\n[PHASE 2] SECONDARY LOADERS (enhance data quality)")
    for loader_file, loader_name in SECONDARY_LOADERS:
        if os.path.exists(loader_file):
            success = run_loader(loader_file, loader_name, is_priority=False)
            results[loader_name] = 'SUCCESS' if success else 'FAILED'

    elapsed = time.time() - start_time

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    successes = sum(1 for v in results.values() if v == 'SUCCESS')
    failures = sum(1 for v in results.values() if v == 'FAILED')
    skipped = sum(1 for v in results.values() if v == 'SKIPPED')

    for loader_name, status in results.items():
        symbol = "[OK]" if status == 'SUCCESS' else "[FAIL]" if status == 'FAILED' else "[SKIP]"
        print(f"{symbol} {loader_name:45} {status}")

    print("\n" + "-"*70)
    print(f"Total time: {elapsed:.1f} seconds")
    print(f"Success: {successes} | Failed: {failures} | Skipped: {skipped}")
    print("="*70 + "\n")

    if failures > 0:
        print("WARNING: Some loaders failed. This may result in incomplete data.")
        print("Review the errors above and re-run if needed.\n")

if __name__ == "__main__":
    main()
