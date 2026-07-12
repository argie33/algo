#!/usr/bin/env python3
import os
import sys
import time

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

sys.path.insert(0, '.')

print("[STEP] Testing dashboard startup sequence...")

print("[1] Parsing arguments...")
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--local', action='store_true')
parser.add_argument('-w', '--watch', nargs='?', const=30, type=int, default=None)
parser.add_argument('--compact', action='store_true')
args = parser.parse_args(['--local'])
print(f"[2] Args: local={args.local}, watch={args.watch}, compact={args.compact}")

print("[3] Importing dashboard modules...")
from dashboard.dashboard import _setup_local_api, run_once
from dashboard.fetchers import load_all
print("[4] Imports successful")

print("[5] Setting up local API...")
start = time.monotonic()
data_source = _setup_local_api()
elapsed = time.monotonic() - start
print(f"[6] Local API setup complete ({elapsed:.2f}s): data_source={data_source}")

print("[7] Testing load_all()...")
start = time.monotonic()
data = load_all()
elapsed = time.monotonic() - start
print(f"[8] load_all() returned in {elapsed:.2f}s, keys={len(data)}")

print("[9] Preparing to call run_once()...")
print("    NOTE: run_once() will hang if there's an issue with Live display or keypress")
print("    We'll give it 20 seconds then timeout")

# Try to run with timeout
import signal
def timeout_handler(signum, frame):
    print("\n[ERROR] run_once() is stuck - killing test")
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(20)

try:
    print("[10] Calling run_once()...")
    run_once(compact=False, data_source="LOCAL")
    print("[11] run_once() returned successfully")
except KeyboardInterrupt:
    print("[INTERRUPT] Interrupted by user")
except SystemExit as e:
    if e.code == 1:
        print("[TIMEOUT] run_once() timed out - stuck!")
    else:
        raise
except Exception as e:
    print(f"[ERROR] run_once() failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
