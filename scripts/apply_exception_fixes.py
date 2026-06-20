#!/usr/bin/env python3
"""
Auto-apply specific exception handler fixes based on context analysis.

Usage:
    python scripts/apply_exception_fixes.py --priority P1 --apply
    python scripts/apply_exception_fixes.py --category DATABASE --apply --limit 50
"""

import argparse
import re
from pathlib import Path
from typing import NamedTuple


class Fix(NamedTuple):
    file_path: Path
    line_num: int
    old_pattern: str
    new_pattern: str
    context_lines: list[str]


def analyze_and_generate_fix(
    file_path: Path, line_num: int, context_start: int, context_end: int
) -> Fix | None:
    """Analyze exception handler and generate fix if applicable."""
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return None

    if line_num < 1 or line_num > len(lines):
        return None

    handler_line = lines[line_num - 1]
    context_text = "".join(lines[context_start : line_num + 1])

    # Determine what to replace this handler with
    if "notify" in context_text.lower() or "alert" in context_text.lower():
        return None  # Skip notifications - keep broad Exception

    if "loader" in context_text.lower() or "load" in context_text.lower():
        return None  # Skip loaders - keep broad Exception

    # Database operations
    if re.search(r"cur\.execute|DatabaseContext|psycopg2", context_text):
        if "(psycopg2" in handler_line:
            return None  # Already fixed
        new = "(psycopg2.DatabaseError, psycopg2.OperationalError)"
        return _create_fix(
            file_path, line_num, handler_line, new, lines[context_start : context_end + 1]
        )

    # API/Network operations
    if re.search(r"requests\.|requests\.get|requests\.post|\.json\(\)", context_text):
        if "requests.RequestException" in handler_line:
            return None  # Already fixed
        new = "(requests.RequestException, requests.Timeout)"
        return _create_fix(
            file_path, line_num, handler_line, new, lines[context_start : context_end + 1]
        )

    # JSON parsing
    if re.search(r"json\.loads|JSONDecodeError", context_text):
        if "json.JSONDecodeError" in handler_line:
            return None  # Already fixed
        new = "(json.JSONDecodeError, ValueError)"
        return _create_fix(
            file_path, line_num, handler_line, new, lines[context_start : context_end + 1]
        )

    # Calculations
    if re.search(r"float\(|int\(|Decimal\(|stdev|mean|statistics", context_text):
        if "ValueError" in handler_line or "ZeroDivisionError" in handler_line:
            return None  # Already fixed
        new = "(ValueError, ZeroDivisionError, TypeError)"
        return _create_fix(
            file_path, line_num, handler_line, new, lines[context_start : context_end + 1]
        )

    return None


def _create_fix(
    file_path: Path, line_num: int, handler_line: str, new_except: str, context_lines: list[str]
) -> Fix | None:
    """Create a Fix object for the given handler."""
    # Extract the exception variable name (if any)
    match = re.search(r"except\s+Exception\s+as\s+(\w+)", handler_line)
    var_name = match.group(1) if match else None

    # Create the replacement
    if var_name:
        new_line = handler_line.replace(
            f"except Exception as {var_name}", f"except {new_except} as {var_name}"
        )
    else:
        new_line = handler_line.replace("except Exception:", f"except {new_except}:")

    if new_line == handler_line:
        return None

    return Fix(
        file_path=file_path,
        line_num=line_num,
        old_pattern=handler_line.rstrip(),
        new_pattern=new_line.rstrip(),
        context_lines=context_lines,
    )


def apply_fix(fix: Fix) -> bool:
    """Apply a single fix to a file."""
    try:
        with open(fix.file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        if fix.line_num < 1 or fix.line_num > len(lines):
            return False

        # Replace the line
        old_content = lines[fix.line_num - 1].rstrip()
        if old_content != fix.old_pattern:
            print(f"[WARN] Line {fix.line_num} mismatch in {fix.file_path}")
            return False

        lines[fix.line_num - 1] = fix.new_pattern + "\n"

        # Write back
        with open(fix.file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return True
    except Exception as e:
        print(f"[ERROR] Failed to apply fix to {fix.file_path}: {e}")
        return False


def find_handlers(file_path: Path) -> list[tuple[int, int]]:
    """Find all broad exception handlers in a file, return (line_num, category)."""
    handlers = []
    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []

    for i, line in enumerate(lines):
        if "except Exception" in line or (re.match(r"\s*except:\s*$", line)):
            handlers.append(i + 1)

    return handlers


def main():
    parser = argparse.ArgumentParser(description="Apply exception handler fixes")
    parser.add_argument(
        "--priority",
        help="Filter by priority (P1, P2, P3)",
        default="P1",
    )
    parser.add_argument(
        "--category", help="Filter by category (DATABASE, API, JSON_PARSING, etc.)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of fixes to apply",
        default=50,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply fixes (default is dry-run)",
    )
    parser.add_argument(
        "--file",
        help="Specific file to process",
    )

    args = parser.parse_args()

    files_to_process = []
    if args.file:
        files_to_process = [Path(args.file)]
    else:
        for base_dir in ["algo", "lambda", "utils", "loaders"]:
            if Path(base_dir).exists():
                files_to_process.extend(Path(base_dir).rglob("*.py"))

    fixes = []
    for file_path in sorted(files_to_process):
        if "__pycache__" in str(file_path):
            continue

        handler_lines = find_handlers(file_path)
        for line_num in handler_lines:
            fix = analyze_and_generate_fix(
                file_path, line_num, max(0, line_num - 20), min(line_num + 3, 10000)
            )
            if fix:
                fixes.append(fix)
                if len(fixes) >= args.limit:
                    break

        if len(fixes) >= args.limit:
            break

    print(f"Found {len(fixes)} fixes to apply")
    print()

    if args.apply:
        applied = 0
        failed = 0
        for fix in fixes:
            if apply_fix(fix):
                applied += 1
                print(f"[OK] {fix.file_path}:{fix.line_num}")
            else:
                failed += 1
                print(f"[FAIL] {fix.file_path}:{fix.line_num}")

        print(f"\nApplied: {applied}, Failed: {failed}")
    else:
        for fix in fixes[:10]:  # Show first 10 as preview
            print(f"{fix.file_path}:{fix.line_num}")
            print(f"  - {fix.old_pattern}")
            print(f"  + {fix.new_pattern}")
            print()

        if len(fixes) > 10:
            print(f"... and {len(fixes) - 10} more fixes (run with --apply to apply)")


if __name__ == "__main__":
    main()
