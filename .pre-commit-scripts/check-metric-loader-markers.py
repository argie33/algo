#!/usr/bin/env python3
"""Pre-commit hook: Enforce marker field existence for all None-returning metric loaders.

Validates:
1. All None metric fields have corresponding *_unavailable_reason fields
2. All data_unavailable assignments include reason field
3. No bare return None without context in metric functions
"""

import re
import sys


def check_metric_loader_markers(filename: str) -> int:
    """Check that metric loaders return proper unavailability markers.

    Returns 0 if compliant, 1 if violations found.
    """
    with open(filename) as f:
        content = f.read()
        lines = content.split("\n")

    violations = []

    # Pattern 1: Check for None assignments without corresponding reason fields
    # This catches patterns like: metrics["roe"] = None (without roe_unavailable_reason)
    for i, line in enumerate(lines, 1):
        # Skip comments and strings
        if line.strip().startswith("#"):
            continue

        # Look for metric field = None patterns
        match = re.search(r'metrics\["(\w+)"\]\s*=\s*None', line)
        if match:
            field_name = match.group(1)

            # Check if there's a corresponding reason field set in next few lines
            reason_field = f"{field_name}_unavailable_reason"
            has_reason = False

            # Check next 10 lines for reason field assignment
            for j in range(i, min(i + 10, len(lines))):
                if f'metrics["{reason_field}"]' in lines[j - 1]:
                    has_reason = True
                    break

            if not has_reason and field_name not in ["symbol", "date", "created_at", "updated_at"]:
                violations.append(
                    f"Line {i}: Field '{field_name}' set to None without {reason_field} marker"
                )

    # Pattern 2: Check for data_unavailable assignments without reason
    for i, line in enumerate(lines, 1):
        if '"data_unavailable": True' in line or "'data_unavailable': True" in line:
            # Look for corresponding reason field in same/next few lines
            has_reason = False
            for j in range(max(0, i - 5), min(i + 5, len(lines))):
                if '"reason":' in lines[j] or "'reason':" in lines[j]:
                    has_reason = True
                    break
            if not has_reason:
                violations.append(
                    f"Line {i}: data_unavailable=True without reason field"
                )

    # Pattern 3: Check for bare return None in metric computation
    for i, line in enumerate(lines, 1):
        # Skip if in comment or string
        if line.strip().startswith("#"):
            continue

        # Look for patterns: return None (not return {...})
        if re.search(r'return\s+None\s*$', line.strip()):
            # Check if this is in a metric computation function
            context = "\n".join(lines[max(0, i - 10) : i])
            if any(
                keyword in context
                for keyword in ["def _compute", "def _calculate", "def _score", "def _get_"]
            ):
                # Check if it's actually raising an error instead
                if "raise" not in lines[i - 1]:
                    violations.append(
                        f"Line {i}: Function returns bare None without context or error"
                    )

    if violations:
        print(f"\n❌ Metric loader marker violations in {filename}:")
        for violation in violations:
            print(f"  {violation}")
        return 1

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: check-metric-loader-markers.py <file1> [<file2> ...]")
        sys.exit(1)

    retval = 0
    for filename in sys.argv[1:]:
        if filename.endswith("_metrics.py"):
            retval |= check_metric_loader_markers(filename)

    sys.exit(retval)
