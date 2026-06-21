#!/usr/bin/env python3
"""Robust CI validation - catch ALL import errors, not just syntax."""

import sys
import subprocess
from pathlib import Path

def test_full_import(description, module_path):
    """Try to actually import and execute a module."""
    print(f"\n[IMPORT] {description}")
    cmd = f"import sys; sys.path.insert(0, '.'); exec(open('{module_path}').read())"
    result = subprocess.run([sys.executable, '-c', cmd], 
                          capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  [PASS]")
        return True
    else:
        # Extract just the error line
        if "ImportError" in result.stderr:
            lines = result.stderr.split('\n')
            for line in lines:
                if "ImportError" in line or "cannot import" in line:
                    print(f"  [FAIL] {line.strip()[:100]}")
                    break
        else:
            print(f"  [FAIL] {result.stderr.split(chr(10))[0][:100]}")
        return False

def main():
    """Run comprehensive import validation."""
    print("\n" + "="*60)
    print("COMPREHENSIVE CI VALIDATION")
    print("="*60)
    
    tests = [
        ("Dashboard main", "tools/dashboard/dashboard.py"),
        ("Fetchers module", "tools/dashboard/fetchers.py"),
        ("Panels __init__", "tools/dashboard/panels/__init__.py"),
        ("Utilities module", "tools/dashboard/utilities.py"),
    ]
    
    results = [test_full_import(desc, path) for desc, path in tests]
    
    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    
    print(f"Results: {passed}/{total} passed")
    
    if passed == total:
        print("\n[SUCCESS] All imports work")
        return 0
    else:
        print(f"\n[FAILURE] {total - passed} modules have import errors")
        print("\nBroken modules need fixing before commit")
        return 1

if __name__ == "__main__":
    sys.exit(main())
