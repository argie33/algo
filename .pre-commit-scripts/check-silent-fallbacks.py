#!/usr/bin/env python3
"""
Enforce fail-fast governance: Prevent silent fallback patterns in loaders and API routes.

This hook catches patterns that violate CLAUDE.md governance rule:
"PRINCIPLE: Fail-fast on missing data. No silent fallbacks."

CRITICAL: Loaders must either:
1. Raise an exception on data unavailability (for CRITICAL data), OR
2. Return explicit dict with data_unavailable=True and reason= (for OPTIONAL data)

❌ FORBIDDEN PATTERNS (silent fallbacks):
  return []                           # Empty array fallback
  return {}                           # Empty dict fallback
  if not data: return []              # Conditional empty return
  if error: return []                 # Conditional empty return

✅ CORRECT PATTERNS:
  raise RuntimeError("reason")        # Fail-fast for CRITICAL data
  return {"data_unavailable": True, "reason": "..."}  # Explicit marker for OPTIONAL data

Files checked: loaders/*.py, lambda/api/routes/*.py, dashboard/**/*.py
"""

import sys
from pathlib import Path
from typing import Any

# Files/paths to CHECK (where strict fail-fast rules apply)
CHECK_PATHS = [
    "loaders/",
    "lambda/api/routes/",
    "dashboard/",
    "algo/trading/",
    "algo/risk/",
]

# Files/paths to SKIP (exceptions where patterns are OK)
SKIP_PATHS = {
    "__pycache__",
    ".git",
    "tests/",
    ".pre-commit-scripts/",
    "venv",
    ".venv",
    "migrations/",
}

# ALLOWED FALLBACK PATTERNS (intentional, safe designs)
ALLOWED_FALLBACK_FILES = {
    "loaders/load_dxy_index.py",  # Known: Yahoo Finance delisted DXY, intentional graceful degradation
    "loaders/load_earnings_calendar.py",  # Known: Optional enrichment, skip on fetch failure
}


def should_check_file(filepath: Path) -> bool:
    """Check if file should be scanned for fallback patterns."""
    str_path = str(filepath)

    # Skip if in SKIP_PATHS
    for skip in SKIP_PATHS:
        if skip in str_path:
            return False

    # Only check if in CHECK_PATHS
    for check in CHECK_PATHS:
        if check in str_path:
            return True

    return False


def is_allowed_fallback_file(filepath: Path) -> bool:
    """Check if this file has an approved fallback pattern (exceptions)."""
    str_path = str(filepath)
    for allowed in ALLOWED_FALLBACK_FILES:
        if allowed in str_path:
            return True
    return False


def check_file_for_fallbacks(filepath: Path) -> list[dict[str, Any]]:
    """Scan file for silent fallback patterns (return [] / return {} without markers)."""
    violations = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    lines = content.splitlines()

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("#"):
            continue

        # Skip lines with data_unavailable (these are OK patterns)
        if "data_unavailable" in line:
            continue

        # VIOLATION: return [] without data_unavailable marker
        if stripped == "return []":
            # Check if previous few lines contain data_unavailable marker
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return []",
                    "message": "Silent fallback: returning empty array without data_unavailable marker",
                    "fix": "Either raise RuntimeError() for CRITICAL data or return {'data_unavailable': True, 'reason': '...'}"
                })

        # VIOLATION: return {} without data_unavailable marker
        if stripped == "return {}":
            context = "\n".join(lines[max(0, line_num-5):line_num])
            if "data_unavailable" not in context:
                violations.append({
                    "file": filepath,
                    "line": line_num,
                    "pattern": "return {}",
                    "message": "Silent fallback: returning empty dict without data_unavailable marker",
                    "fix": "Either raise RuntimeError() for CRITICAL data or return {'data_unavailable': True, 'reason': '...'}"
                })

    return violations


def main() -> int:
    """Check Python files for silent fallback patterns."""
    repo_root = Path.cwd()
    violations = []

    # Find all Python files to check
    for py_file in repo_root.rglob("*.py"):
        if not should_check_file(py_file):
            continue

        # Skip allowed fallback files (documented exceptions)
        if is_allowed_fallback_file(py_file):
            continue

        violations.extend(check_file_for_fallbacks(py_file))

    if violations:
        print("[FAILED] FALLBACK ENFORCEMENT FAILED")
        print("Found silent fallback patterns (violate fail-fast governance):\n")

        for v in sorted(violations, key=lambda x: str(x["file"])):
            print(f"  {v['file']}:{v['line']}")
            print(f"    Pattern: {v['pattern']}")
            print(f"    Issue: {v['message']}")
            print(f"    Fix: {v['fix']}\n")

        print("[CONTEXT] CLAUDE.md Rule:")
        print("  PRINCIPLE: Fail-fast on missing data. No silent fallbacks.")
        print("  Loaders must return explicit data_unavailable markers")
        print("  or raise exceptions for missing CRITICAL data.\n")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
