#!/usr/bin/env python3
import os
import sys

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

sys.path.insert(0, '.')

import time

print("[TEST] Testing dashboard rendering...")

# First load fetcher data
print("[1] Loading fetcher data...")
start = time.monotonic()
import dashboard.fetchers
data = dashboard.fetchers.load_all()
elapsed = time.monotonic() - start
print(f"[2] Fetcher data loaded in {elapsed:.2f}s, keys: {list(data.keys())}")

# Now try to render
print("[3] Importing render modules...")
start = time.monotonic()
from dashboard.renderers import render_dashboard, render_dashboard_body
elapsed = time.monotonic() - start
print(f"[4] Render modules imported in {elapsed:.2f}s")

print("[5] Rendering dashboard...")
start = time.monotonic()
try:
    layout = render_dashboard_body(
        data,
        elapsed_sec=0.5,
        frame=0,
        view_mode="normal",
        watch_interval=None,
        compact=False,
        data_source="dev"
    )
    elapsed = time.monotonic() - start
    print(f"[6] Dashboard rendered in {elapsed:.2f}s")
    print(f"[7] Layout type: {type(layout)}")
except Exception as e:
    elapsed = time.monotonic() - start
    print(f"[ERROR] Rendering failed after {elapsed:.2f}s:")
    print(f"  {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
