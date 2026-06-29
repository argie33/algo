#!/usr/bin/env python3
"""Pre-commit check: Enforce strict=True on safe_float/safe_int in finance paths.

Finance-critical paths (loaders, risk calculations, signals, position sizing)
must use strict=True on safe_float/safe_int to ensure data parsing errors
surface immediately instead of silently defaulting to invalid values.

Pattern violations to catch:
  - safe_float(...) without strict=True in finance paths
  - safe_int(...) without strict=True in finance paths
  - safe_bool(...) without strict=True in finance paths
"""

import re
import sys


def check_strict_conversion(filepath: str) -> list[str]:
    """Check file for missing strict=True on safe data conversion.

    Returns list of violations with line numbers.
    """
    violations = []

    # Only check finance-critical paths
    finance_paths = (
        "loaders/",
        "algo/risk/",
        "algo/signals/",
        "algo/trading/",
        "dashboard/fetchers",
    )
    if not filepath.endswith(".py") or not any(fp in filepath for fp in finance_paths):
        return violations

    try:
        with open(filepath) as f:
            lines = f.readlines()
    except Exception as e:
        return [f"Could not read file: {e}"]

    # Pattern: safe_float/safe_int/safe_bool call WITHOUT strict=True
    # Allowed patterns:
    #   safe_float(x, strict=True, ...)
    #   safe_float(x, field_name="...", strict=True)
    #   safe_float(x, strict=True)
    # Disallowed:
    #   safe_float(x)
    #   safe_float(x, default=0)
    #   safe_float(x, field_name="...")

    for i, line in enumerate(lines, 1):
        # Match calls to safe_float, safe_int, safe_bool
        match = re.search(r"\b(safe_float|safe_int|safe_bool)\s*\(", line)
        if not match:
            continue

        func_name = match.group(1)

        # Extract the call expression (from first paren to matching close paren)
        # This is a simplified check—if line contains both open and close, check it
        if "(" in line and ")" in line:
            call_start = line.find(func_name + "(")
            call_end = line.rfind(")")

            if call_start >= 0 and call_end > call_start:
                call_expr = line[call_start : call_end + 1]

                # Check if strict=True is present in the call
                if "strict=True" not in call_expr and "strict = True" not in call_expr:
                    # Special case: allow no-arg calls like safe_float(v, default=None) in display-only code
                    # But flag them anyway since they're in finance paths
                    violations.append(
                        f"  Line {i}: {func_name}() missing strict=True. "
                        f"Finance paths must fail on parse errors, not fallback to defaults. "
                        f"Call: {call_expr.strip()}"
                    )

    return violations


if __name__ == "__main__":
    all_violations = []

    for filepath in sys.argv[1:]:
        violations = check_strict_conversion(filepath)
        if violations:
            all_violations.append(f"{filepath}:")
            all_violations.extend(violations)

    if all_violations:
        print("Missing strict=True on safe data conversion in finance paths:")
        print("\n".join(all_violations))
        print(
            "\nFix: Add strict=True to all safe_float/safe_int/safe_bool calls in "
            "loaders/, algo/risk/, algo/signals/, algo/trading/, and dashboard/fetchers. "
            "See utils/safe_data_conversion.py for details."
        )
        sys.exit(1)

    sys.exit(0)
