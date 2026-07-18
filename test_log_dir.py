#!/usr/bin/env python3
"""Test if log directory creation hangs."""

import os
import sys
import io

# Fix encoding for Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.getcwd())

try:
    print("1. Testing makedirs...")
    _log_dir = os.path.expanduser("~/.algo/logs")
    print(f"   Log dir path: {_log_dir}")
    os.makedirs(_log_dir, exist_ok=True)
    print("   OK: makedirs completed")

    print("2. Testing RotatingFileHandler...")
    import logging.handlers
    _log_file = os.path.join(_log_dir, "dashboard-local.log")
    print(f"   Log file path: {_log_file}")
    _handler = logging.handlers.RotatingFileHandler(_log_file, encoding="utf-8", maxBytes=10*1024*1024, backupCount=3)
    print("   OK: RotatingFileHandler created")

    print("SUCCESS!")

except Exception as e:
    import traceback
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
