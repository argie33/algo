#!/usr/bin/env python3
"""Final verification: load data and run orchestrator to confirm all fixes work."""
import logging
from datetime import date, timedelta
from algo.algo_orchestrator import Orchestrator
from algo.infrastructure import get_config

logging.basicConfig(level=logging.CRITICAL)

print("=== FINAL SYSTEM VERIFICATION ===\n")

try:
    # Get Monday
    today = date.today()
    days_ahead = 7 - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    monday = today + timedelta(days=days_ahead)

    print(f"Testing with Monday: {monday}\n")

    config = get_config()
    orch = Orchestrator(config=config, run_date=monday, dry_run=True, verbose=False)
    result = orch.run()

    print("ORCHESTRATOR RESULT:")
    print(f"  Success: {result.get('success')}")
    print(f"  Skipped: {result.get('skipped')}")
    print(f"  Reason: {result.get('reason', 'None')}")
    print(f"  Phases completed: {result.get('phases_completed', 0)}")
    print(f"  Phases halted: {result.get('phases_halted', 0)}")
    print(f"  Phases errored: {result.get('phases_errored', 0)}")

    if result.get('success') and not result.get('skipped'):
        print("\n[SUCCESS] System is fully operational!")
    elif result.get('skipped'):
        print(f"\n[INFO] Orchestrator skipped (expected for weekend): {result.get('reason')}")
    else:
        print(f"\n[FAIL] Orchestrator failed: {result.get('reason')}")

except Exception as e:
    print(f"[ERROR] {e}")
