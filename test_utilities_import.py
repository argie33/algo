#!/usr/bin/env python3
"""Test utilities import with fresh Python process."""

import os
import sys
import subprocess
import time

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

# Test in subprocess to ensure fresh Python process
code = """
import os
import sys

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

sys.path.insert(0, os.getcwd())

print("Importing utilities...")
import dashboard.utilities
print("OK: utilities imported successfully")
"""

proc = subprocess.Popen(
    [sys.executable, "-c", code],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

try:
    stdout, stderr = proc.communicate(timeout=10)
    print(stdout)
    if stderr:
        print("STDERR:", stderr)
    if proc.returncode == 0:
        print("\nSUCCESS: Dashboard utilities module imported successfully!")
    else:
        print(f"\nFAILED: Process exited with code {proc.returncode}")
except subprocess.TimeoutExpired:
    proc.kill()
    print("TIMEOUT: Import took longer than 10 seconds")
    sys.exit(1)
