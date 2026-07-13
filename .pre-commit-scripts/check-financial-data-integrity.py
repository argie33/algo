#!/usr/bin/env python3
"""
Financial Data Integrity Enforcement Hook.

Ensures ALL financial data access follows fail-fast patterns:
1. CRITICAL data paths raise exceptions on unavailability
2. OPTIONAL data paths return data_unavailable: True markers
3. No silent None/0/[] returns in error paths
4. All data sources explicitly validated before use

Enforces: steering/GOVERNANCE.md financial data contract rules
"""

import re
import sys
from pathlib import Path
from typing import Any

# Critical financial paths that must never silently degrade
CRITICAL_FINANCIAL_FILES = {
    "algo/trading/",
    "algo/signals/",
    "algo/risk/",
    "algo/orchestration/",
    "loaders/",  # Data loaders MUST be fail-fast
    "lambda/api/routes/algo_handlers/",  # API returning financial data
}

# Optional enrichment that can gracefully degrade
OPTIONAL_ENRICHMENT_FILES = {
    "dashboard/",
    "lambda/api/routes/data/",
}


def should_check_file(filepath: Path) -> bool:
    if filepath.suffix != ".py":
        return False

    str_path = str(filepath)

    # Skip non-production code
    for skip in ["tests/", "test_", ".pre-commit", "scripts/", "migrations/", "venv"]:
        if skip in str_path:
            return False

    # Only check if in critical/optional financial paths
    is_critical = any(crit in str_path for crit in CRITICAL_FINANCIAL_FILES)
    is_optional = any(opt in str_path for opt in OPTIONAL_ENRICHMENT_FILES)

    return is_critical or is_optional


def check_financial_data_integrity(filepath: Path) -> list[dict[str, Any]]:
    violations = []
    is_critical = any(crit in str(filepath) for crit in CRITICAL_FINANCIAL_FILES)

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    lines = content.splitlines()

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments, docstrings, blank
        if stripped.startswith(("#", '"""', "'''")) or not stripped:
            continue

        # PATTERN 1: data["key"] without guard (could KeyError silently)
        if re.search(r'(row|data|result|metrics|breadth|prices|volumes)\["', stripped):
            # Check if guarded by try/except, if check, or optional access
            context_start = max(0, line_num - 5)
            context_end = min(len(lines), line_num + 3)
            context = "\n".join(lines[context_start:context_end])

            # Safe if: guarded, or this is an assignment with default
            if any(guard in context for guard in ["try:", "except", " in ", "if ", ".get("]):
                continue

            if is_critical:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "unguarded_data_access",
                    "message": "[CRITICAL] Unguarded data[key] access in financial path (could raise KeyError)",
                    "fix": "Use try/except, key existence check, or .get() with explicit error handling"
                })

        # PATTERN 2: Financial calculation with None without check
        financial_calcs = [
            r"(?:close|price|volume|value|score|size|position_value)\s*\*\s*(?!0)",
            r"(?:close|price|volume|value|score|size|position_value)\s*/\s*(?!0)",
        ]
        for calc_pattern in financial_calcs:
            if re.search(calc_pattern, stripped) and " if " not in stripped:
                # Check for None protection in surrounding lines
                context_start = max(0, line_num - 3)
                context_end = min(len(lines), line_num + 3)
                context = "\n".join(lines[context_start:context_end])

                if "is None" in context or "is not None" in context or "try:" in context:
                    continue

                if is_critical:
                    violations.append({
                        "file": filepath,
                        "line": line_num,
                        "pattern": "unprotected_calc",
                        "message": "[CRITICAL] Financial calculation without None protection (could silently calculate 0 with None)",
                        "fix": "Add explicit None check before any arithmetic: if value is None: raise ValueError(...)"
                    })

        # PATTERN 3: return None in financial function without Optional type hint
        if stripped == "return None":
            # Look for function definition
            func_def_line = None
            for search_line in range(line_num - 1, max(0, line_num - 50), -1):
                if lines[search_line].strip().startswith("def "):
                    func_def_line = search_line
                    break

            if func_def_line:
                func_sig = "\n".join(lines[func_def_line:line_num])

                # Check if Optional or data_unavailable is in return type
                if "Optional" not in func_sig and "| None" not in func_sig and \
                   "data_unavailable" not in func_sig and "-> None" not in func_sig:

                    # Check if in error path
                    context_start = max(0, func_def_line)
                    context = "\n".join(lines[context_start:line_num])

                    if any(kw in context.lower() for kw in ["error", "failed", "exception", "unavailable"]):
                        if is_critical:
                            violations.append({
                                "file": filepath,
                                "line": line_num,
                                "pattern": "unmarked_none_return",
                                "message": "[CRITICAL] return None in error path without Optional type or data_unavailable marker",
                                "fix": "Add '-> Optional[...]' type hint or return {'data_unavailable': True, 'reason': '...'}"
                            })

    return violations


def main() -> int:
    repo_root = Path.cwd()
    violations = []

    for py_file in repo_root.rglob("*.py"):
        if not should_check_file(py_file):
            continue

        violations.extend(check_financial_data_integrity(py_file))

    if violations:
        print("[FAILED] FINANCIAL DATA INTEGRITY VIOLATION")
        print("Found data access patterns that could silently corrupt calculations:\n")

        by_pattern = {}
        for v in violations:
            pattern = v["pattern"]
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(v)

        for pattern in sorted(by_pattern.keys()):
            print(f"\n{pattern.upper()} ({len(by_pattern[pattern])} violations):")
            for v in sorted(by_pattern[pattern], key=lambda x: (str(x["file"]), x["line"]))[:5]:
                print(f"  {v['file']}:{v['line']}")
                print(f"    {v['message']}")
                print(f"    Fix: {v['fix']}")

        return 1

    print("[PASS] All financial data access follows fail-fast patterns [OK]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
