#!/usr/bin/env python3
"""Test full dashboard import."""

import os
import sys
import subprocess

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

code = """
import os
import sys

os.environ["LOCAL_MODE"] = "true"
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

sys.path.insert(0, os.getcwd())

print("Importing dashboard...")
import dashboard.dashboard
print("OK: dashboard module imported successfully")

print("Testing main function can be called...")
from dashboard.dashboard import main
print("OK: main function accessible")

print("Testing load_all function...")
from dashboard.fetchers import load_all
print("OK: load_all function accessible")
"""

proc = subprocess.Popen(
    [sys.executable, "-c", code],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

try:
    stdout, stderr = proc.communicate(timeout=15)
    print(stdout)
    if stderr:
        print("STDERR:", stderr)
    if proc.returncode == 0:
        print("\nSUCCESS: Dashboard fully imported and functions accessible!")
    else:
        print(f"\nFAILED: Process exited with code {proc.returncode}")
except subprocess.TimeoutExpired:
    proc.kill()
    print("TIMEOUT: Import took longer than 15 seconds")
    sys.exit(1)
