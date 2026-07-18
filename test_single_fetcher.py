#!/usr/bin/env python3
"""Measure single fetcher performance with details."""
import sys
import time
import os
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='[%(name)s] %(message)s')

sys.path.insert(0, '.')

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'

from dashboard.fetchers import FETCHERS

# Test a single fetcher
fetcher_name = 'cfg'
fetcher_fn = FETCHERS[fetcher_name]

print(f"[TEST] Testing fetcher: {fetcher_name}")
print(f"[TEST] Function: {fetcher_fn.__name__}\n")

t0 = time.time()
result = fetcher_fn(None)
elapsed = time.time() - t0

print(f"\n[TEST] Fetcher took {elapsed:.3f}s")
print(f"[TEST] Result: {type(result).__name__} with {len(result)} keys")
if '_error' in result:
    print(f"[TEST] ERROR: {result['_error']}")
else:
    print(f"[TEST] SUCCESS")
