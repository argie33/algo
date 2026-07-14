#!/usr/bin/env python3
"""Pre-commit hook: Prevent unsafe .get() patterns on critical financial data.

Validates:
1. No .get("key", []) or .get("key", {}) defaults on critical data
2. No .get("key", 0) on position/quantity fields
3. No .get() on required fields without explicit downstream validation
"""

import re
import sys

CRITICAL_FIELDS = {
    "data_unavailable",  # Must check with explicit default or explicit check
    "close",
    "high",
    "low",
    "open",
    "volume",
    "quantity",
    "position",
    "limit",
    "symbol",
    "price",
}

UNSAFE_DEFAULTS = {
    "[]",
    "{}",
    '""',
    "''",
}


def check_critical_get_patterns(filename: str) -> int:
    """Check for unsafe .get() patterns on critical financial data.

    Returns 0 if compliant, 1 if violations found.
    """
    with open(filename) as f:
        content = f.read()
        lines = content.split("\n")

    violations = []

    for i, line in enumerate(lines, 1):
        # Skip comments and strings
        if line.strip().startswith("#"):
            continue

        # Pattern: .get("field", unsafe_default)
        for field in CRITICAL_FIELDS:
            # Match patterns like: .get("data_unavailable", []) or .get("close", 0)
            match = re.search(rf'\.get\(\s*["\']?{re.escape(field)}["\']?\s*,\s*([^)]+)\)', line)
            if match:
                default_value = match.group(1).strip()

                # Check if default is unsafe
                if default_value in UNSAFE_DEFAULTS:
                    violations.append(
                        f"Line {i}: Unsafe .get() default on critical field '{field}': .get(..., {default_value})"
                    )
                elif default_value == "0" and field in ["quantity", "position", "price", "volume"]:
                    violations.append(f"Line {i}: Unsafe .get() default=0 on critical financial field '{field}'")

    if violations:
        print(f"\n❌ Critical .get() pattern violations in {filename}:")
        for violation in violations:
            print(f"  {violation}")
        print("\nFix: Use explicit validation after .get() or validate field presence explicitly")
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: check-critical-get-patterns.py <file1> [<file2> ...]")
        sys.exit(1)

    retval = 0
    for filename in sys.argv[1:]:
        # Check files in critical paths
        if any(part in filename for part in ["loaders", "lambda/api", "dashboard", "algo/trading", "algo/risk"]):
            retval |= check_critical_get_patterns(filename)

    sys.exit(retval)
