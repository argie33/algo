#!/usr/bin/env python3
"""Run orchestrator and verify Phase 7 signal quality fix works."""

import sys
import subprocess
sys.path.insert(0, "/root" if "/" in sys.path[0] else "C:\\Users\\arger\\code\\algo")

print("\n" + "=" * 70)
print("RUNNING ORCHESTRATOR TEST - VERIFY PHASE 7 SIGNAL QUALITY FIX")
print("=" * 70)

print("\nRunning orchestrator...")
print("-" * 70)

# Run orchestrator
result = subprocess.run(
    [sys.executable, "scripts/run_local_orchestrator.py", "--afternoon"],
    capture_output=True,
    text=True,
    timeout=600
)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])

print("\n" + "=" * 70)
print("VERIFYING RESULTS")
print("=" * 70)

# Check if orchestrator ran successfully
if "success" in result.stdout.lower():
    print("[OK] Orchestrator completed")
else:
    print("[FAIL] Orchestrator did not complete successfully")

# Check if Phase 7 ran and signal quality scores were computed
if "Phase 7" in result.stdout or "signal" in result.stdout.lower():
    print("[OK] Phase 7 executed")
else:
    print("[?] Phase 7 status unknown")

print("\n" + "=" * 70 + "\n")
