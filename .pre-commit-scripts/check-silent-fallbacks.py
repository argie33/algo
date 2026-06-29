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

        # ========== PATTERN 4: Unsafe .get() WITH DEFAULTS on financial data ==========
        # Only flag .get() calls that have explicit defaults (the real problem)
        # Normal .get() without defaults is OK (returns None which callers should handle)
        get_with_default = re.search(r'\.get\([^,]+,\s*(["\']|0|None|\[\]|{}|Decimal)', stripped)
        if get_with_default:
            # Check if this is likely financial data
            is_financial_get = any(pattern in stripped for pattern in [
                "row.get(", "data.get(", "info.get(", "breadth.get(", "metrics.get(",
                "prices.get(", "volumes.get(", "position.get(", "score.get("
            ])
            if is_financial_get:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": ".get(..., default)",
                    "message": "Unsafe .get() with default on financial data (silent fallback if key missing)",
                    "fix": "Check key presence explicitly: if 'key' in dict and dict['key'] is not None: ..."
                })

        # ========== PATTERN 5: Silent None return ==========
        if stripped == "return None" or re.match(r"return\s+None\s*$", stripped):
            context_start = max(0, line_num - 15)
            context = "\n".join(lines[context_start:line_num])

            # Skip if it's in a try/except context (error handling)
            if "except" in context or "try:" in context:
                continue

            # Skip if function is Optional[T] (returns None as valid state)
            # Search backward for "def " to find function definition
            func_def_line = None
            for search_line in range(line_num - 1, max(0, line_num - 50), -1):
                if lines[search_line].strip().startswith("def "):
                    func_def_line = search_line
                    break

            if func_def_line is not None:
                # Get full function signature (might span multiple lines)
                func_sig = "\n".join(lines[func_def_line:line_num])
                # Check if function explicitly returns Optional/Union with None
                if ("-> " in func_sig and ("| None" in func_sig or "Optional" in func_sig)) or \
                   ("-> None:" in func_sig):  # Function that returns only None
                    continue

            # Skip if comment indicates None is intentional (cache miss, no data, etc.)
            if any(phrase in context.lower() for phrase in [
                "cache miss", "not cached", "no data", "optional", "not provided",
                "expected state", "no error", "validation passed", "no duplicate",
                "can proceed", "market closed", "fresh data"
            ]):
                continue

            # Only flag if in financial function AND context suggests error path
            is_financial = any(kw in context.lower() for kw in [
                "fetch", "load", "get_", "price", "metric", "data", "auth", "token",
                "calculate", "score", "signal", "validate"
            ])

            is_error_path = any(phrase in context.lower() for phrase in [
                "error", "failed", "unavailable", "exception", "corrupted", "invalid state"
            ])

            if is_financial and is_error_path:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return None",
                    "message": "Silent None return in error path (caller cannot distinguish 'no data' from 'error')",
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
