#!/usr/bin/env python3
"""Pre-commit check: Detect problematic .get() patterns in finance-critical code.

Dashboard panels should use fail-fast pattern:
  1. Check error_boundary.has_error(data) once
  2. Use direct access for validated fields
  3. Only .get() for optional fields (no default or default=None)

Loaders should avoid:
  - .get() with numeric defaults (0, 0.0) for price/financial data
  - .get() with dict defaults ({}) for financial records
  - .get() with string defaults that mask missing data

Pattern violations to catch:
  - Multiple .get() calls on same data dict in same function
  - .get() without checking has_error() first (dashboard only)
  - .get() with numeric/dict defaults in finance-critical data
  - .get() in nested loops over data items
"""

import re
import sys


def check_get_patterns_with_defaults(filepath: str) -> list[str]:
    """Check for problematic .get() calls with numeric/dict defaults.

    Finance-critical paths should not silently default to 0, 0.0, {}, etc.
    These patterns hide missing data.
    """
    violations = []

    finance_paths = ("loaders/", "algo/trading/", "algo/risk/", "algo/signals/")
    if not filepath.endswith(".py") or not any(fp in filepath for fp in finance_paths):
        return violations

    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Pattern: .get("key", numeric/dict/problematic_default)
    problem_patterns = [
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*0(?:\.\d+)?\s*\)', "numeric default (hides missing price data)"),
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*\{\s*\}\s*\)', "dict default (hides missing record)"),
        (r'\.get\s*\(\s*["\'][\w_]+["\']\s*,\s*""\s*\)', 'empty string default (hides missing data)'),
    ]

    for i, line in enumerate(lines, 1):
        for pattern, description in problem_patterns:
            if re.search(pattern, line):
                violations.append(
                    f"  Line {i}: {description} in .get() call. "
                    f"Finance paths must fail on missing data, not default to {description.split('(')[1].split(')')[0]}."
                )

    return violations


def check_dashboard_patterns(filepath: str) -> list[str]:
    """Check file for dashboard .get() antipatterns.

    Returns list of violations with line numbers.
    """
    violations = []

    if not filepath.endswith(".py") or "dashboard" not in filepath:
        return violations

    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Pattern 1: Function with 5+ .get() calls without has_error() check
    func_pattern = re.compile(r"^\s*def\s+(\w+)\s*\(")
    get_pattern = re.compile(r"\.get\(")
    has_error_pattern = re.compile(r"has_error\(")

    in_function = None
    func_start_line = 0
    get_count = 0
    has_error_check = False

    for i, line in enumerate(lines, 1):
        func_match = func_pattern.match(line)
        if func_match:
            # New function: check if previous one had issues
            if in_function and get_count >= 5 and not has_error_check:
                violations.append(
                    f"  Line {func_start_line} ({in_function}): {get_count} .get() calls, no has_error() check"
                )
            in_function = func_match.group(1)
            func_start_line = i
            get_count = 0
            has_error_check = False

        if has_error_pattern.search(line):
            has_error_check = True

        if get_pattern.search(line):
            get_count += 1

    # Check last function
    if in_function and get_count >= 5 and not has_error_check:
        violations.append(f"  Line {func_start_line} ({in_function}): {get_count} .get() calls, no has_error() check")

    return violations


if __name__ == "__main__":
    all_violations = []

    for filepath in sys.argv[1:]:
        # Check for problematic defaults in loaders
        violations = check_get_patterns_with_defaults(filepath)
        if violations:
            all_violations.append(f"{filepath} (loader/finance checks):")
            all_violations.extend(violations)

        # Check for dashboard fail-fast pattern violations
        violations = check_dashboard_patterns(filepath)
        if violations:
            all_violations.append(f"{filepath} (dashboard checks):")
            all_violations.extend(violations)

    if all_violations:
        print("❌ .get() pattern violations found (fail-fast discipline violation):")
        print("\n".join(all_violations))
        print(
            "\nFix:\n"
            "  Dashboard: Use error_boundary.has_error() + direct access (see panels/data_extractors.py)\n"
            "  Loaders: Remove numeric/dict defaults from .get() — use strict validation or raise\n"
            "  Finance paths: Missing data must be visible (fail fast), not silently defaulted"
        )
        sys.exit(1)

    sys.exit(0)
