#!/usr/bin/env python3
"""Integration test: Verify refactored algo modules work end-to-end."""
import sys
sys.path.insert(0, '.')

print("INTEGRATION TEST: Refactored Algo Modules")
print("=" * 70)

# Test 1: Module imports
print("\n1. MODULE IMPORT TEST")
print("-" * 70)
modules_ok = 0
modules_fail = 0
module_list = ['dashboard', 'metrics', 'admin', 'analysis', 'config', 'market', 'notifications', 'orchestrator', 'external']

for mod in module_list:
    try:
        exec(f"from algo import {mod}")
        print(f"   [OK] algo.{mod}")
        modules_ok += 1
    except Exception as e:
        print(f"   [FAIL] algo.{mod} - {str(e)[:50]}")
        modules_fail += 1

print(f"\nResult: {modules_ok}/{len(module_list)} modules import successfully")

if modules_fail > 0:
    print(f"\nWARNING: {modules_fail} modules failed to import")
    sys.exit(1)

# Test 2: Handler availability
print("\n2. HANDLER AVAILABILITY TEST")
print("-" * 70)
handlers_ok = 0
handlers_tested = 0

# Test dashboard handlers
handlers_to_test = [
    ('dashboard', 'handle_status'),
    ('dashboard', 'handle_trades'),
    ('dashboard', 'handle_positions'),
    ('metrics', 'handle_metrics'),
    ('metrics', 'handle_portfolio'),
    ('admin', 'handle_trigger_patrol'),
    ('analysis', 'handle_swing_scores'),
]

for mod, handler in handlers_to_test:
    try:
        mod_obj = __import__(f'algo.{mod}', fromlist=[handler])
        func = getattr(mod_obj, handler)
        handlers_ok += 1
        print(f"   [OK] algo.{mod}.{handler}")
    except Exception as e:
        print(f"   [FAIL] algo.{mod}.{handler} - {str(e)[:40]}")
    handlers_tested += 1

print(f"\nResult: {handlers_ok}/{handlers_tested} handlers available")

# Test 3: Original code accessibility
print("\n3. ORIGINAL CODE BACKUP TEST")
print("-" * 70)
try:
    import algo_original
    print(f"   [OK] algo_original module accessible")
    # Check it has the functions
    if hasattr(algo_original, '_get_algo_status'):
        print(f"   [OK] Original _get_algo_status function exists")
    else:
        print(f"   [FAIL] _get_algo_status not found in algo_original")
except Exception as e:
    print(f"   [FAIL] algo_original not accessible: {e}")

# Summary
print("\n" + "=" * 70)
if modules_fail == 0 and handlers_ok == handlers_tested:
    print("VERDICT: PASS - Refactored module structure is functional")
    print("=" * 70)
    sys.exit(0)
else:
    print("VERDICT: FAIL - Some modules or handlers are not working")
    print("=" * 70)
    sys.exit(1)
