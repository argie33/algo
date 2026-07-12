#!/usr/bin/env python3
import os
import sys
import signal

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

sys.path.insert(0, '.')

print("[TEST] Testing watch mode with timeout...")

def timeout_handler(signum, frame):
    print("\n[TEST] Timeout reached - dashboard is stuck!")
    sys.exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(45)  # 45 second timeout

try:
    from dashboard.dashboard import run_watch
    print("[TEST] Running watch mode for 20 seconds...")
    # This should NOT return unless we hit 'q' key
    # Since we can't send keys, we expect it to hang
    run_watch(interval=10, compact=False, data_source="LOCAL")
except KeyboardInterrupt:
    print("[TEST] Interrupted")
except Exception as e:
    print(f"[TEST] Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
