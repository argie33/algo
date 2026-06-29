#!/usr/bin/env python3
"""
Enforce fail-fast governance: Prevent ALL silent fallback patterns across entire codebase.

This hook catches patterns that violate CLAUDE.md governance rule:
"PRINCIPLE: Fail-fast on missing data. No silent fallbacks."

CRITICAL: Code must either:
1. Raise an exception on data unavailability (for CRITICAL data), OR
2. Return explicit dict with data_unavailable=True and reason= (for OPTIONAL data)

❌ FORBIDDEN PATTERNS (silent fallbacks):
  return []                           # Empty array fallback
  return {}                           # Empty dict fallback
  return 0 / return Decimal(0)        # Hardcoded zero for financial data
  return None (w/o context)           # Silent None
  .get("key")                         # Unsafe default on financial data
  if not data: return []              # Conditional empty return
  if error: return []                 # Conditional empty return

✅ CORRECT PATTERNS:
  raise RuntimeError("reason")        # Fail-fast for CRITICAL data
  raise ValueError("reason")          # Explicit error for validation
  return {"data_unavailable": True, "reason": "..."}  # Explicit marker for OPTIONAL data
  if key in dict and dict[key] is not None:  # Explicit key check (not .get())

Files checked: ALL Python files in repo except tests/, venv/
"""

import re
import sys
from pathlib import Path
from typing import Any

# Files/paths to CHECK (ALL Python files except skip list)
# This is enforced EVERYWHERE in the codebase
CHECK_PATHS = [
    ".",  # ALL Python files
]

# Files/paths to SKIP (tests, venv, etc. only)
SKIP_PATHS = {
    "__pycache__",
    ".git",
    "tests/",
    "test_",  # test_*.py files
    ".pre-commit-scripts/",
    "venv",
    ".venv",
    "migrations/",
    "scripts/",  # utility scripts
    ".pytest_cache",
    "node_modules",
}


def should_check_file(filepath: Path) -> bool:
    """Check if file should be scanned for fallback patterns."""
    # Only check Python files
    if filepath.suffix != ".py":
        return False

    str_path = str(filepath)

    # Skip if in SKIP_PATHS
    for skip in SKIP_PATHS:
        if skip in str_path:
            return False

    return True


def check_file_for_fallbacks(filepath: Path) -> list[dict[str, Any]]:
    """Scan file for ALL silent fallback patterns."""
    violations = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    lines = content.splitlines()

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments, blank lines, and docstrings
        if stripped.startswith(("#", '"""', "'''")) or not stripped:
            continue

        # Skip lines with explicit error handling (raise, data_unavailable, except)
        if any(kw in stripped for kw in ["raise ", "data_unavailable", "except ", "try:", "logger.error", "logger.critical"]):
            continue

        # ========== PATTERN 1: return [] without marker ==========
        if stripped == "return []":
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context and "raise" not in context:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return []",
                    "message": "Silent fallback: returning empty array without data_unavailable marker or exception",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 2: return {} without marker ==========
        if stripped == "return {}":
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context and "raise" not in context:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return {}",
                    "message": "Silent fallback: returning empty dict without data_unavailable marker or exception",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 3: return 0 / Decimal(0) for financial data ==========
        if re.match(r"^\s*return\s+(0|Decimal\(0\)|0\.0|0\.)", stripped):
            # Check if this is in a financial function (heuristic: function name or nearby comments suggest financial)
            context_start = max(0, line_num - 20)
            context = "\n".join(lines[context_start:line_num])
            is_financial = any(kw in context.lower() for kw in [
                "position", "score", "size", "price", "volume", "volatility", "beta", "metric",
                "signal", "technical", "financial", "market", "risk", "exposure", "exposure_pct"
            ])
            if is_financial:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return 0",
                    "message": "Hardcoded zero return in financial function (ambiguous: could mean 'no data' or 'error')",
                    "fix": "Raise exception for CRITICAL data OR return {'data_unavailable': True, 'reason': '...'}"
                })

        # ========== PATTERN 4: Unsafe .get() on financial data (STRICT: only flag obvious cases) ==========
        # Only flag very specific patterns that are clearly financial data access
        obvious_financial_get = any(pattern in stripped for pattern in [
            "row.get(", "data.get(", "info.get(", "breadth.get(", "metrics.get(",
            "prices.get(", "volumes.get(", "position.get(", "score.get("
        ])
        if obvious_financial_get:
            violations.append({
                "file": filepath,
                "line": line_num,
                "pattern": ".get()",
                "message": "Unsafe .get() on financial data (returns None silently if key missing)",
                "fix": "Use explicit check: if 'key' in dict and dict['key'] is not None: ..."
            })

        # ========== PATTERN 5: Silent None return ==========
        if stripped == "return None" or re.match(r"return\s+None\s*$", stripped):
            context_start = max(0, line_num - 10)
            context = "\n".join(lines[context_start:line_num])
            # Skip if it's in a try/except context (error handling)
            if "except" not in context and "try:" not in context:
                is_financial = any(kw in context.lower() for kw in [
                    "fetch", "load", "get_", "price", "metric", "data", "auth", "token",
                    "calculate", "score", "signal", "validate"
                ])
                if is_financial:
                    violations.append({
                        "file": filepath,
                        "line": line_num,
                        "pattern": "return None",
                        "message": "Silent None return (caller cannot distinguish 'no data' from 'error')",
                        "fix": "Raise exception OR return {'data_unavailable': True, 'reason': '...'}"
                    })

    return violations


def main() -> int:
    """Check Python files for silent fallback patterns."""
    repo_root = Path.cwd()
    violations = []

    # Find all Python files to check (everywhere, NO exceptions)
    for py_file in repo_root.rglob("*.py"):
        if not should_check_file(py_file):
            continue

        violations.extend(check_file_for_fallbacks(py_file))

    if violations:
        print("[FAILED] FAIL-FAST ENFORCEMENT VIOLATION")
        print("Found silent fallback patterns that violate governance:\n")

        # Group by pattern type
        by_pattern = {}
        for v in violations:
            pattern = v['pattern']
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(v)

        for pattern in sorted(by_pattern.keys()):
            print(f"\n{pattern.upper()} ({len(by_pattern[pattern])} violations):")
            for v in sorted(by_pattern[pattern], key=lambda x: (str(x["file"]), x["line"]))[:10]:  # Show first 10
                print(f"  {v['file']}:{v['line']}")
                print(f"    {v['message']}")
                print(f"    Fix: {v['fix']}")

        if len(violations) > 10:
            print(f"\n  ... and {len(violations) - 10} more violations")

        print("\n[GOVERNANCE] CLAUDE.md Rule:")
        print("  'PRINCIPLE: Fail-fast on missing data. No silent fallbacks.'")
        print("\n  Code must EITHER:")
        print("    1. Raise exception (raise RuntimeError/ValueError) for CRITICAL data")
        print("    2. Return explicit marker {'data_unavailable': True, 'reason': '...'} for OPTIONAL data")
        print("\n  NO:")
        print("    - return [] or return {} without markers")
        print("    - return 0 for financial calculations")
        print("    - return None without explaining why")
        print("    - .get() without explicit key validation")
        print("\n  See: steering/FAIL_FAST_VIOLATIONS_CATALOG_2026_06_29.md")

        return 1

    print("[PASS] All files comply with fail-fast governance ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
