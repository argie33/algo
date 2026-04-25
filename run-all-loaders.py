#!/usr/bin/env python3
"""Run all data loaders in sequence with error handling"""

import subprocess
import sys
import os
import io
import time
from datetime import datetime

# Fix Unicode encoding on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

loaders = [
    ('loaddailycompanydata.py', 'Earnings Estimates'),
    ('loadecondata.py', 'Economic Data'),
    ('loadfactormetrics.py', 'Factor Metrics'),
    ('loadbuysellweekly.py', 'Buy/Sell Signals'),
]

print("=" * 70)
print("DATA LOADER SUITE - Starting all loaders in sequence")
print("=" * 70)
print()

results = {}
start_time = time.time()

for loader_file, loader_name in loaders:
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting {loader_name}...")
    print(f"  File: {loader_file}")
    print("-" * 70)

    try:
        result = subprocess.run(
            [sys.executable, loader_file],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per loader
        )

        if result.returncode == 0:
            print(f"[OK] {loader_name} completed successfully")
            results[loader_name] = 'SUCCESS'
            # Print last few lines of output
            lines = result.stdout.split('\n')
            for line in lines[-5:]:
                if line.strip():
                    print(f"     {line}")
        else:
            print(f"[ERROR] {loader_name} failed with exit code {result.returncode}")
            results[loader_name] = f'FAILED (exit {result.returncode})'
            # Print error output
            if result.stderr:
                for line in result.stderr.split('\n')[-10:]:
                    if line.strip():
                        print(f"     ERROR: {line}")

    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {loader_name} timed out after 5 minutes")
        results[loader_name] = 'TIMEOUT'
    except Exception as e:
        print(f"[EXCEPTION] {loader_name} raised exception: {e}")
        results[loader_name] = f'EXCEPTION: {str(e)[:50]}'

    print()

elapsed = time.time() - start_time

print("=" * 70)
print("SUMMARY")
print("=" * 70)
for loader_name, status in results.items():
    symbol = "[OK]" if status == 'SUCCESS' else "[FAIL]"
    print(f"{symbol} {loader_name:25} {status}")

print()
print(f"Total time: {elapsed:.1f} seconds")
print()

# Check if any succeeded
successes = sum(1 for s in results.values() if s == 'SUCCESS')
print(f"Result: {successes}/{len(loaders)} loaders completed successfully")
