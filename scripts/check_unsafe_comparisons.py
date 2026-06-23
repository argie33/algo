#!/usr/bin/env python3
"""Pre-commit hook to catch unsafe .get() comparisons without type validation.

Detects patterns like:
  UNSAFE: value.get("key") >= 100
  UNSAFE: data.get("field", 0) > 5
  SAFE: safe_float(data.get("field")) >= 100
  SAFE: int(data.get("count", 0)) > 5

This prevents TypeError: '>=' not supported between instances of 'dict' and 'int'
"""

import re
import sys
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def check_file(filepath: str) -> list[str]:
    """Check a single file for unsafe comparisons.

    Returns list of error messages.
    """
    errors = []
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError):
        return errors

    lines = content.split("\n")

    # Pattern: .get(...) followed by comparison operator, without safe_float/safe_int wrapping
    # Look for lines that have .get() and comparison but NOT safe_float/safe_int
    for i, line in enumerate(lines, 1):
        # Skip comments and docstrings
        if line.strip().startswith("#") or '"""' in line or "'''" in line:
            continue

        # Skip test files
        if "test_" in filepath:
            continue

        # Pattern 1: .get(...) directly followed by >, <, >=, <=
        # But exclude:
        #   - safe_float/safe_int wrapped calls
        #   - int(...) or float(...) wrapped calls
        #   - == and != comparisons with strings/None
        #   - .get() in string formatting
        if ".get(" in line and any(op in line for op in [">=", "<=", ">", "<"]):
            # Exclude safe patterns
            if any(safe in line for safe in ["safe_float", "safe_int", "int(", "float("]):
                continue

            # Exclude string comparisons and formatting
            if '==' in line or '!=' in line or "f\"" in line or "f'" in line:
                continue

            # Find the .get(...) call and check if there's a comparison near it
            match = re.search(r'\.get\([^)]*\)[^,;}\]]*[<>=!]', line)
            if match:
                # Exclude patterns like: .get('key', '') != "" or .get('key') == "something"
                if "== " in line or '!= ' in line or "==" in line or "!=" in line:
                    continue

                errors.append(f"{filepath}:{i}: Unsafe .get() comparison without safe_float/safe_int validation")
                errors.append(f"    {line.strip()}")

    return errors


def main() -> int:
    """Check all Python files in the repo."""
    python_files = list(Path(".").rglob("*.py"))

    # Exclude directories and the check script itself
    exclude_dirs = {".git", ".claude", "migrations", "tests", ".pytest_cache", "node_modules"}
    exclude_files = {"scripts/check_unsafe_comparisons.py"}
    python_files = [
        f
        for f in python_files
        if not any(part in exclude_dirs for part in f.parts)
        and str(f).replace("\\", "/") not in exclude_files
    ]

    all_errors = []
    for filepath in sorted(python_files):
        errors = check_file(str(filepath))
        all_errors.extend(errors)

    if all_errors:
        print("[FAILED] UNSAFE COMPARISONS DETECTED:\n")
        for error in all_errors:
            print(error)
        unsafe_count = len([e for e in all_errors if ':' in e and 'Unsafe' in e])
        print(f"\n[BLOCKED] Found {unsafe_count} unsafe comparison(s)")
        print(
            "\nFIX: Wrap .get() results with safe_float() or safe_int() before comparisons:\n"
            "    value = safe_float(data.get('key'), default=None)\n"
            "    if value is not None and value >= 100:\n"
            "        ...\n"
        )
        return 1

    print("[OK] No unsafe comparisons found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
