#!/usr/bin/env python3
"""Measure individual fetcher performance."""
import sys
import time
import os

sys.path.insert(0, '.')

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'

from dashboard.fetchers import FETCHERS

print("[SPEED] Testing individual fetcher performance...")
print(f"[SPEED] Found {len(FETCHERS)} fetchers\n")

times = {}
for name, fn in sorted(FETCHERS.items()):
    t0 = time.time()
    try:
        result = fn(None)
        elapsed = time.time() - t0
        is_error = isinstance(result, dict) and '_error' in result
        status = "ERROR" if is_error else "OK"
        times[name] = elapsed
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [{status}]")
    except Exception as e:
        elapsed = time.time() - t0
        times[name] = elapsed
        print(f"[SPEED] {name:20s}: {elapsed:7.3f}s [EXCEPTION]")

print("\n[SPEED] SLOWEST FETCHERS:")
sorted_times = sorted(times.items(), key=lambda x: -x[1])
for name, elapsed in sorted_times[:10]:
    print(f"[SPEED]   {name:20s}: {elapsed:.3f}s")

total = sum(times.values())
print(f"\n[SPEED] Total time: {total:.3f}s")
print(f"[SPEED] Average: {total/len(times):.3f}s per fetcher")
