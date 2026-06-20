#!/usr/bin/env python3
"""
Systematically fix broad exception handlers across the codebase.

Analyzes context of each `except Exception:` or bare `except:` and suggests
or applies specific exception types based on the surrounding code.

Usage:
    python scripts/fix_broad_exception_handlers.py --file <path> [--apply]
    python scripts/fix_broad_exception_handlers.py --all [--apply] [--category DATABASE]
"""

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional


class ExceptionHandler(NamedTuple):
    line_num: int
    context_start: int
    context_end: int
    exception_type: str
    category: str
    suggested_fix: str
    priority: str


def analyze_exception_context(lines: list[str], handler_line: int) -> tuple[str, str, str]:
    """
    Analyze the context around an exception handler to determine:
    1. What category of error it's handling (DATABASE, API, etc.)
    2. What specific exceptions it should catch
    3. Priority level for fixing

    Returns: (category, suggested_fix, priority)
    """
    # Look back up to 20 lines for context
    context_start = max(0, handler_line - 20)
    context_lines = lines[context_start:handler_line + 1]
    context_text = "\n".join(context_lines)

    # Determine category based on what operations precede the handler
    if re.search(r"cur\.execute|DatabaseContext|psycopg2", context_text):
        category = "DATABASE"
        suggested = "(psycopg2.DatabaseError, psycopg2.OperationalError)"
        priority = "P1"
    elif re.search(r"requests\.|requests\.get|requests\.post", context_text):
        category = "API"
        suggested = "(requests.RequestException, requests.Timeout)"
        priority = "P1"
    elif re.search(r"json\.loads|\.json\(\)|JSONDecodeError", context_text):
        category = "JSON_PARSING"
        suggested = "(json.JSONDecodeError, ValueError)"
        priority = "P2"
    elif re.search(r"notify|alert|logger\.|send.*alert|send.*email", context_text, re.I):
        category = "NOTIFICATION"
        suggested = "Exception"  # Keep broad - non-critical
        priority = "SKIP"
    elif re.search(r"float\(|int\(|Decimal\(|stdev|mean|statistics", context_text):
        category = "CALCULATION"
        suggested = "(ValueError, ZeroDivisionError, TypeError)"
        priority = "P2"
    elif re.search(r"open\(|read\(|write\(|pathlib|Path", context_text):
        category = "FILE_IO"
        suggested = "(FileNotFoundError, IOError, OSError)"
        priority = "P3"
    elif re.search(r"loader|load_.*|data.*load|fetch.*data", context_text, re.I):
        category = "LOADER"
        suggested = "Exception"  # Keep broad - non-critical background task
        priority = "SKIP"
    else:
        category = "UNKNOWN"
        suggested = "Exception"  # Default - needs manual review
        priority = "REVIEW"

    return category, suggested, priority


def find_exception_handlers(file_path: Path) -> list[ExceptionHandler]:
    """Find all broad exception handlers in a file."""
    handlers = []
    try:
        with open(file_path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return []

    for i, line in enumerate(lines):
        if "except Exception" in line or (re.match(r"\s*except:\s*$", line)):
            # Extract exception type
            match = re.search(r"except\s+(\w+)?\s+as\s+(\w+)", line)
            exc_type = match.group(1) if match else "Exception" if "except Exception" in line else "bare"

            category, suggested, priority = analyze_exception_context(lines, i)

            handler = ExceptionHandler(
                line_num=i + 1,
                context_start=max(0, i - 5),
                context_end=min(len(lines), i + 3),
                exception_type=exc_type,
                category=category,
                suggested_fix=suggested,
                priority=priority,
            )
            handlers.append(handler)

    return handlers


def print_handlers_summary(file_path: Path, handlers: list[ExceptionHandler]):
    """Print a summary of found exception handlers."""
    if not handlers:
        print(f"[OK] No broad exception handlers found in {file_path}")
        return

    print(f"\n[SCAN] Found {len(handlers)} broad exception handlers in {file_path}")
    print(f"{'Line':>6} {'Priority':>8} {'Category':>15} {'Current':>12} {'Suggested':>40}")
    print("-" * 85)

    for h in handlers:
        if h.priority != "SKIP":
            print(
                f"{h.line_num:>6} {h.priority:>8} {h.category:>15} "
                f"except {h.exception_type:>10} -> {h.suggested_fix:>40}"
            )

    # Summary by priority
    by_priority = {}
    for h in handlers:
        by_priority.setdefault(h.priority, 0)
        by_priority[h.priority] += 1

    print(f"\n[SUMMARY]")
    for priority in ["P1", "P2", "P3", "REVIEW"]:
        if priority in by_priority:
            print(f"   {priority}: {by_priority[priority]} handlers")
    if "SKIP" in by_priority:
        print(f"   SKIP (non-critical): {by_priority['SKIP']} handlers")


def show_context(file_path: Path, handler: ExceptionHandler):
    """Show context around an exception handler."""
    try:
        with open(file_path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except Exception:
        return

    print(f"\n  Context for line {handler.line_num}:")
    for i in range(handler.context_start, handler.context_end):
        prefix = ">>> " if i == handler.line_num - 1 else "    "
        if i < len(lines):
            print(f"{prefix}{i + 1:4}: {lines[i].rstrip()}")


def main():
    parser = argparse.ArgumentParser(
        description="Fix broad exception handlers across the codebase"
    )
    parser.add_argument("--file", help="Path to specific Python file to analyze")
    parser.add_argument(
        "--all", action="store_true", help="Analyze all Python files in algo/, lambda/, utils/, loaders/"
    )
    parser.add_argument(
        "--category", help="Filter by category (DATABASE, API, JSON_PARSING, etc.)"
    )
    parser.add_argument(
        "--priority", help="Filter by priority (P1, P2, P3, REVIEW, SKIP)"
    )
    parser.add_argument("--apply", action="store_true", help="Apply fixes (not yet implemented)")
    parser.add_argument("--verbose", action="store_true", help="Show context for each handler")

    args = parser.parse_args()

    if not args.file and not args.all:
        parser.print_help()
        return

    if args.apply:
        print("[WARN] --apply not yet implemented. Run without --apply to preview fixes first.")
        return

    files_to_analyze = []
    if args.file:
        files_to_analyze = [Path(args.file)]
    elif args.all:
        base_dirs = ["algo", "lambda", "utils", "loaders"]
        for base_dir in base_dirs:
            if Path(base_dir).exists():
                files_to_analyze.extend(Path(base_dir).rglob("*.py"))

    total_handlers = 0
    by_category = {}

    for file_path in sorted(files_to_analyze):
        if "__pycache__" in str(file_path):
            continue

        handlers = find_exception_handlers(file_path)
        if not handlers:
            continue

        # Filter by category/priority if requested
        if args.category:
            handlers = [h for h in handlers if h.category == args.category]
        if args.priority:
            handlers = [h for h in handlers if h.priority == args.priority]

        if handlers:
            print_handlers_summary(file_path, handlers)
            total_handlers += len(handlers)

            for h in handlers:
                by_category.setdefault(h.category, 0)
                by_category[h.category] += 1

            if args.verbose:
                for h in handlers:
                    if h.priority != "SKIP":
                        show_context(file_path, h)

    print(f"\n\n[TOTAL SUMMARY]")
    print(f"{'='*50}")
    print(f"Total broad exception handlers found: {total_handlers}")
    print(f"\nBy category:")
    for category in sorted(by_category.keys()):
        print(f"  {category:>15}: {by_category[category]:>3}")


if __name__ == "__main__":
    main()
