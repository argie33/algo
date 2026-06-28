#!/usr/bin/env python3
"""Robust CI validation - catch ALL import errors, not just syntax."""

import subprocess
import sys


def test_module_import(description: str, import_statement: str) -> bool:
    """Try to import a module using proper package semantics."""
    print(f"\n[IMPORT] {description}")
    cmd = f"import sys; sys.path.insert(0, '.'); {import_statement}"
    result = subprocess.run([sys.executable, "-c", cmd], capture_output=True, text=True)

    if result.returncode == 0:
        print("  [PASS]")
        return True
    else:
        if "ImportError" in result.stderr or "ModuleNotFoundError" in result.stderr:
            lines = result.stderr.split("\n")
            for line in lines:
                if "ImportError" in line or "ModuleNotFoundError" in line or "cannot import" in line:
                    print(f"  [FAIL] {line.strip()[:100]}")
                    break
        else:
            print(f"  [FAIL] {result.stderr.split(chr(10))[0][:100]}")
        return False


def main() -> int:
    """Run comprehensive import validation."""
    print("\n" + "=" * 60)
    print("COMPREHENSIVE CI VALIDATION")
    print("=" * 60)

    tests = [
        ("Dashboard main", "from dashboard import dashboard"),
        ("Fetchers module", "from dashboard import fetchers"),
        ("Panels __init__", "from dashboard import panels"),
        ("Utilities module", "from dashboard import utilities"),
        ("Panel registry", "from dashboard import panel_registry"),
        ("Error boundary", "from dashboard import error_boundary"),
        ("Formatters", "from dashboard import formatters"),
        ("API data layer", "from dashboard import api_data_layer"),
        ("Cognito auth", "from dashboard import cognito_auth"),
        ("Panel helpers", "from dashboard.panels import _helpers"),
        ("Panel base", "from dashboard.panels import panel_base"),
        ("Circuit panel", "from dashboard.panels import circuit"),
        ("Economic panel", "from dashboard.panels import economic"),
        ("Health panel", "from dashboard.panels import health"),
        ("Market panel", "from dashboard.panels import market"),
        ("Portfolio panel", "from dashboard.panels import portfolio"),
        ("Positions panel", "from dashboard.panels import positions"),
        ("Sectors panel", "from dashboard.panels import sectors"),
        ("Signals panel", "from dashboard.panels import signals"),
        ("Trades panel", "from dashboard.panels import trades"),
    ]

    results = [test_module_import(desc, stmt) for desc, stmt in tests]

    print("\n" + "=" * 60)
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
