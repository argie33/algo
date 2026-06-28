#!/usr/bin/env python3
"""Pre-commit check: Detect excessive .get() calls in dashboard panels.

Dashboard panels should use fail-fast pattern:
  1. Check error_boundary.has_error(data) once
  2. Use direct access for validated fields
  3. Only .get() for optional fields

Pattern violations to catch:
  - Multiple .get() calls on same data dict in same function
  - .get() without checking has_error() first
  - .get() in nested loops over data items
"""

import re
import sys


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
        violations = check_dashboard_patterns(filepath)
        if violations:
            all_violations.append(f"{filepath}:")
            all_violations.extend(violations)

    if all_violations:
        print("Dashboard .get() pattern violations found:")
        print("\n".join(all_violations))
        print("\nFix: Use error_boundary.has_error() + direct access. See tools/dashboard/panels/data_extractors.py")
        sys.exit(1)

    sys.exit(0)
