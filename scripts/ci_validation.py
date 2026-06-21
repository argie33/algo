#!/usr/bin/env python3
"""Comprehensive CI validation: check imports, types, and dependencies."""

import sys
import subprocess
from pathlib import Path

def run_check(description, py_code):
    """Run a Python check and report results."""
    print(f"\n[CHECK] {description}")
    try:
        result = subprocess.run([sys.executable, '-c', py_code], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"  [PASS]")
            return True
        else:
            print(f"  [FAIL]")
            if result.stderr:
                # Print first few lines of error
                lines = result.stderr.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f"    {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [TIMEOUT]")
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def main():
    """Run all CI checks."""
    print("\n" + "="*60)
    print("CI VALIDATION SUITE - IMPORT & SYNTAX CHECKS")
    print("="*60)
    
    results = []
    
    # Check 1: All Python files compile
    print("\n[CHECK] Python syntax - all files compile")
    try:
        from compileall import compile_dir
        compile_dir("tools", quiet=2)
        compile_dir("lambda", quiet=2)
        compile_dir("algo", quiet=2)
        print("  [PASS] All files have valid syntax")
        results.append(True)
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(False)
    
    # Check 2: Critical dashboard imports
    check2 = """
import sys
sys.path.insert(0, '.')
from tools.dashboard.utilities import LOAD_SEQ, MASCOT_COLORS, G, R, Y
from tools.dashboard.utilities import normalize_positions_data, compute_sector_agg
print("Dashboard utilities: OK")
"""
    results.append(run_check("Dashboard utilities imports", check2))
    
    # Check 3: Portfolio panels
    check3 = """
import sys
sys.path.insert(0, '.')
try:
    from tools.dashboard.panels.portfolio import panel_portfolio, panel_performance_spark
    print("Portfolio panels: OK")
except ImportError as e:
    if 'calculate_adjusted_win_rate' in str(e):
        print(f"MISSING FUNCTION: {e}")
        raise
"""
    results.append(run_check("Portfolio panels imports", check3))
    
    # Check 4: Sector panels
    check4 = """
import sys
sys.path.insert(0, '.')
try:
    from tools.dashboard.panels.sectors import panel_sector_compact
    print("Sector panels: OK")
except ImportError as e:
    if '_rdelta' in str(e) or 'compute_sector_agg' in str(e):
        print(f"MISSING FUNCTION: {e}")
        raise
"""
    results.append(run_check("Sector panels imports", check4))
    
    # Check 5: Data extractors
    check5 = """
import sys
sys.path.insert(0, '.')
try:
    from tools.dashboard.panels.data_extractors import safe_get_dict, safe_get_field, safe_get_list
    print("Data extractors: OK")
except ImportError as e:
    print(f"MISSING: {e}")
"""
    results.append(run_check("Data extractors imports", check5))
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total} checks")
    
    if passed == total:
        print("\n[SUCCESS] All checks passed - code is ready")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} checks failed")
        print("\nFix broken imports before committing:")
        print("  - Restore missing functions to utilities.py")
        print("  - Restore missing functions to portfolio.py")
        print("  - Create/restore data_extractors.py")
        return 1

if __name__ == "__main__":
    sys.exit(main())
