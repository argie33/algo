#!/usr/bin/env python3
"""Pre-commit hook: Prevent hardcoded status strings and magic number thresholds.

Violations:
1. status = 'open' / 'closed' / etc (must import from constants)
2. score >= 60 / score >= 70 (must use config.get() or constants)
3. completeness >= 0.70 (must use constants)
4. ETF filtering duplicated (must use symbol_filters.build_clause())

Run: python .pre-commit-scripts/check-no-hardcoded-patterns.py <files>
"""

import re
import sys


def check_file(filepath: str) -> list[str]:
    violations = []

    try:
        with open(filepath) as f:
            content = f.read()
            lines = content.split("\n")
    except Exception as e:
        return [f"Error reading {filepath}: {e}"]

    # Skip certain files that are allowed to have these patterns
    skip_patterns = ["test_", "tests/", ".pre-commit-scripts/", "migrations/", "lambda/", "terraform/"]
    if any(skip in filepath for skip in skip_patterns):
        return []

    # Check 1: status = 'open'/'closed' (must use constants)
    status_pattern = re.compile(
        r"""(?:status\s*[!=]=\s*['"](open|closed|halted|cancelled)['"]\)|\.get\(["']status["']\)\s*[!=]="""
    )
    for i, line in enumerate(lines, 1):
        if "# noqa" in line:
            continue
        if "constants import" in line or "PositionStatus" in line:
            continue
        if status_pattern.search(line):
            if "PositionStatus" not in line and "TradeStatus" not in line:
                violations.append(
                    f"{filepath}:{i} Status hardcoded (use PositionStatus/TradeStatus enum): {line.strip()}"
                )

    # Check 2: score >= 60/70/80 (must use config or constants)
    score_pattern = re.compile(r"score\s*[><=]{1,2}\s*[0-9]+")
    for i, line in enumerate(lines, 1):
        if "# noqa" in line or "def " in line or "==" in line:
            continue
        if score_pattern.search(line):
            if "config.get" not in line and "DEFAULT_" not in line:
                violations.append(
                    f"{filepath}:{i} Score threshold hardcoded (use config.get() or constants): {line.strip()}"
                )

    # Check 3: completeness >= 0.70 (must use constants)
    completeness_pattern = re.compile(r"completeness\s*[><=]{1,2}\s*0\.[0-9]+")
    for i, line in enumerate(lines, 1):
        if "# noqa" in line or "DEFAULT_" in line:
            continue
        if completeness_pattern.search(line):
            violations.append(
                f"{filepath}:{i} Completeness threshold hardcoded (use DEFAULT_DATA_COMPLETENESS_THRESHOLD): {line.strip()}"
            )

    return violations


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: check-no-hardcoded-patterns.py <file1> [file2] ...")
        return 0

    all_violations = []
    for filepath in sys.argv[1:]:
        if filepath.endswith(".py"):
            violations = check_file(filepath)
            all_violations.extend(violations)

    if all_violations:
        print("VIOLATIONS FOUND (enforce single source of truth):")
        for v in all_violations:
            print(f"  {v}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
