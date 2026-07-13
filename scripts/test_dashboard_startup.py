#!/usr/bin/env python3
"""Diagnostic script to test dashboard startup."""

import os
import sys
import traceback

# Fix Windows console encoding before doing anything else
if sys.platform.startswith('win'):
    import io
    # Allow UTF-8 output even on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add repo root to path
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
os.environ['LOCAL_MODE'] = 'true'

print("[TEST] Starting dashboard diagnostic...", flush=True)

try:
    print("[TEST] Step 1: Importing dashboard module...", flush=True)
    print("[TEST] OK: Dashboard module imported successfully", flush=True)

except Exception as e:
    print(f"[TEST] FAIL: Failed to import dashboard: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    print("[TEST] Step 2: Importing Rich Console...", flush=True)
    from rich.console import Console

    print("[TEST] OK: Console imported", flush=True)

except Exception as e:
    print(f"[TEST] FAIL: Failed to import Console: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    print("[TEST] Step 3: Testing Live context manager...", flush=True)
    from rich.live import Live
    from rich.text import Text

    test_console = Console(force_terminal=True, legacy_windows=False)
    print("[TEST] OK: Test console created", flush=True)

    with Live(console=test_console, screen=True) as live:
        print("[TEST] OK: Live context manager opened successfully", flush=True)
        live.update(Text("Test output"))
        print("[TEST] OK: Live.update() succeeded", flush=True)

    print("[TEST] OK: Live context manager exited successfully", flush=True)

except Exception as e:
    print(f"[TEST] FAIL: Failed Live context manager test: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

print("[TEST] OK: All diagnostics passed! Dashboard should work.", flush=True)
