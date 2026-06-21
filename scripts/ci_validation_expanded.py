#!/usr/bin/env python3
"""EXPANDED CI validation - test dashboard, lambda, loaders, algo, utils."""

import sys
import importlib

def test_import(description, module_name):
    """Test if a module can be imported."""
    print(f"[TEST] {description}...", end=" ")
    try:
        importlib.import_module(module_name)
        print("[PASS]")
        return True
    except ImportError as e:
        print(f"[FAIL]")
        print(f"  Error: {str(e)[:80]}")
        return False
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}")
        return False

def main():
    """Run expanded validation across all modules."""
    print("\n" + "="*70)
    print("EXPANDED CI VALIDATION - ALL MODULES")
    print("="*70 + "\n")
    
    tests = [
        # Dashboard (original tests)
        ("Dashboard utilities", "tools.dashboard.utilities"),
        ("Dashboard fetchers", "tools.dashboard.fetchers"),
        ("Dashboard panels", "tools.dashboard.panels"),
        ("Dashboard main", "tools.dashboard.dashboard"),
        
        # Lambda API
        ("Lambda API routes", "lambda.api.routes"),
        ("Lambda API health", "lambda.api.routes.health"),
        ("Lambda API algo", "lambda.api.routes.algo"),
        
        # Algo modules
        ("Algo orchestrator", "algo.orchestrator.orchestrator"),
        ("Algo Phase 0", "algo.orchestrator.phase0_startup"),
        ("Algo Phase 8", "algo.orchestrator.phase8_entry_execution"),
        
        # Loaders
        ("Loaders", "loaders"),
        ("Load positions", "loaders.load_positions"),
        ("Load signals", "loaders.load_signals"),
        ("Load metrics", "loaders.load_metrics_raw"),
        
        # Utils
        ("Utils contexts", "utils.contexts"),
        ("Utils safe conversion", "utils.safe_data_conversion"),
    ]
    
    sys.path.insert(0, '.')
    results = [test_import(desc, module) for desc, module in tests]
    
    print("\n" + "="*70)
    passed = sum(results)
    total = len(results)
    pct = int(100 * passed / total)
    
    print(f"Results: {passed}/{total} modules working ({pct}%)\n")
    
    if passed == total:
        print("[SUCCESS] All modules importable")
        return 0
    else:
        failed = total - passed
        print(f"[FAILURE] {failed} modules have import errors\n")
        print("BROKEN MODULES:")
        for i, (desc, _) in enumerate(tests):
            if not results[i]:
                print(f"  - {desc}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
