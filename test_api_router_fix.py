#!/usr/bin/env python3
"""Test script to verify static imports fix for critical routes."""

import sys
sys.path.insert(0, 'lambda/api')

import api_router

print("=" * 60)
print("API ROUTER STATIC IMPORTS TEST")
print("=" * 60)

status = api_router.get_import_status()
print("\nImport Status:")
print(f"  Total routes: {status['total_routes']}")
print(f"  Successful routes: {status['successful_routes']}")
print(f"  Failed routes: {status['failed_routes']}")
print(f"  Critical failures: {status['critical_failures']}")

print("\nCritical Routes Status:")
for route in api_router._CRITICAL_ROUTES:
    imported = "YES (static)" if route in api_router._AVAILABLE_ROUTES else "FAILED"
    print(f"  {route}: {imported}")

if status['failed_modules']:
    print(f"\nFailed Optional Routes ({len(status['failed_modules'])}):")
    for module in status['failed_modules']:
        error = status['failed_details'].get(module, 'unknown')
        print(f"  - {module}: {error[:80]}")

print(f"\nPublic Handlers: {list(api_router.PUBLIC_HANDLERS.keys())}")
print(f"Authenticated Handlers: {len(api_router.HANDLERS)} routes")

print("\n" + "=" * 60)
if status['critical_failures']:
    print("FAILED: Critical routes could not be imported!")
    sys.exit(1)
else:
    print("PASSED: All critical routes imported successfully!")
    print("Optional routes are loaded gracefully with error handling.")
    sys.exit(0)
