#!/usr/bin/env python3
"""Validate that critical modules can be imported."""

import sys

sys.path.insert(0, ".")
errors = []

test_modules = [
    "config.credential_manager",
    "config.thresholds",
    "utils.optimal_loader",
    "utils.data.source_router",
    "algo.algo_orchestrator",
]

for module in test_modules:
    try:
        __import__(module)
        print(f"OK: {module}")
    except Exception as e:
        errors.append(f"{module}: {str(e)[:100]}")
        print(f"FAIL: {module}")

if errors:
    print("\nImport validation failed:")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)

print("\nOK: All critical modules can be imported")
