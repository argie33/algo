#!/usr/bin/env python3
import os
import sys

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

sys.path.insert(0, '.')

import time

print("[TEST] Importing dashboard modules...")
start = time.monotonic()

# Just try importing the fetchers module
try:
    print("[1] Starting imports...")
    import dashboard.fetchers
    elapsed = time.monotonic() - start
    print(f"[2] dashboard.fetchers imported in {elapsed:.2f}s")

    print("[3] Calling load_all...")
    start = time.monotonic()
    result = dashboard.fetchers.load_all()
    elapsed = time.monotonic() - start

    print(f"[4] load_all completed in {elapsed:.2f}s")
    print(f"[5] Result keys: {list(result.keys())[:10]}")

    # Check for errors
    errors = {k: v.get('_error', '')[:80] for k, v in result.items() if isinstance(v, dict) and '_error' in v}
    if errors:
        print(f"[6] Errors: {errors}")
    else:
        print(f"[6] No errors!")

except Exception as e:
    elapsed = time.monotonic() - start
    print(f"[ERROR] {type(e).__name__} after {elapsed:.2f}s:")
    print(f"  {e}")
    import traceback
    traceback.print_exc()
