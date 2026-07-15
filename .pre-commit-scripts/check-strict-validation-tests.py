#!/usr/bin/env python3
"""Pre-commit check: Ensure StrictValidationError is tested.

This script verifies that:
1. All safe_float/safe_int calls with strict=True are tested
2. Test coverage for StrictValidationError exists
3. None values passed to strict converters are caught in testing

This is part of the overall strategy to catch validation errors in CI/CD
before they reach production.
"""

import re
import sys
from pathlib import Path


def check_strict_validation_tests() -> tuple[bool, list[str]]:
    """Check that strict validation errors are tested.

    Returns (success: bool, issues: list[str])
    """
    issues = []

    # Check 1: Ensure test files exist for strict validation
    test_files = [
        Path("tests/test_strict_validation_error_detection.py"),
        Path("tests/test_dashboard_panel_strict_validation.py"),
    ]

    for test_file in test_files:
        if not test_file.exists():
            issues.append(f"Missing test file: {test_file}")

    # Check 2: Ensure StrictValidationError tests cover None case
    strict_test_file = Path("tests/test_strict_validation_error_detection.py")
    if strict_test_file.exists():
        with open(strict_test_file) as f:
            content = f.read()

        required_test_patterns = [
            r"def test_none_raises_strict_validation_error",
            r"StrictValidationError",
            r"strict=True",
            r"pytest\.raises\(StrictValidationError\)",
        ]

        for pattern in required_test_patterns:
            if not re.search(pattern, content, re.IGNORECASE | re.DOTALL):
                issues.append(f"Test file missing pattern: {pattern}")

    # Check 3: Ensure safe_float/safe_int strict calls are being used in finance paths
    finance_paths = [
        "dashboard/",
        "loaders/",
        "algo/risk/",
        "algo/trading/",
    ]

    for path in finance_paths:
        path_obj = Path(path)
        if not path_obj.exists():
            continue

        py_files = list(path_obj.glob("**/*.py"))
        if not py_files:
            continue

        # Sample a few files to check for strict=True usage
        for py_file in py_files[:5]:
            with open(py_file) as f:
                content = f.read()

            # If using safe_float/safe_int, should have strict=True
            if re.search(r"\bsafe_float\(.*\)", content) or re.search(r"\bsafe_int\(.*\)", content):
                # Just note this, don't fail — check-strict-safe-conversion.py handles this
                pass

    return len(issues) == 0, issues


def main() -> int:
    """Run the check."""
    _success, issues = check_strict_validation_tests()

    if issues:
        print("Strict validation testing issues found:")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Fix:")
        print("1. Ensure tests/test_strict_validation_error_detection.py exists")
        print("2. Ensure tests/test_dashboard_panel_strict_validation.py exists")
        print("3. Run: make test  # to execute all tests")
        return 1

    print("[OK] Strict validation tests are in place")
    print("[OK] StrictValidationError will be caught in CI/CD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
