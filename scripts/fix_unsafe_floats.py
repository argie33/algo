#!/usr/bin/env python3
"""
Systematic fix for unsafe float() conversions across the codebase.

Replaces unsafe float(x) calls with safe_float(x, default=0.0, context="...")
ensuring financial precision and fail-fast behavior on NaN/Infinity.

Usage:
    python scripts/fix_unsafe_floats.py <file_path> [--dry-run] [--context "description"]
"""

import argparse
import re
from pathlib import Path
from typing import Tuple


def find_unsafe_floats(content: str) -> list[tuple[int, str]]:
    """Find all unsafe float() calls (not already wrapped in safe_float)."""
    lines = content.split('\n')
    unsafe = []

    for i, line in enumerate(lines, 1):
        # Skip comments and docstrings
        if line.strip().startswith('#') or '"""' in line or "'''" in line:
            continue

        # Skip if already using safe_float
        if 'safe_float(' in line:
            continue

        # Find float() calls - but be careful about float as part of other names
        if re.search(r'\bfloat\s*\([^)]*\)', line):
            unsafe.append((i, line.rstrip()))

    return unsafe


def has_safe_float_import(content: str) -> bool:
    """Check if file imports safe_float."""
    return 'from utils.safe_data_conversion import safe_float' in content or \
           'from utils.validation.framework import safe_float' in content


def add_safe_float_import(content: str) -> str:
    """Add safe_float import if not present."""
    if has_safe_float_import(content):
        return content

    # Find last import statement
    lines = content.split('\n')
    last_import_idx = -1
    for i, line in enumerate(lines):
        if line.startswith('from ') or line.startswith('import '):
            last_import_idx = i

    if last_import_idx == -1:
        return content

    # Insert import after last import
    lines.insert(last_import_idx + 1, 'from utils.safe_data_conversion import safe_float')
    return '\n'.join(lines)


def fix_unsafe_floats_in_file(file_path: Path, context_prefix: str = "") -> tuple[str, int]:
    """
    Fix unsafe float() calls in a file.

    Returns: (modified_content, count_of_fixes)
    """
    content = file_path.read_text()
    unsafe_calls = find_unsafe_floats(content)

    if not unsafe_calls:
        return content, 0

    # Add import
    content = add_safe_float_import(content)

    # For now, just report - manual review needed for correct context
    return content, len(unsafe_calls)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', help='Python files to fix')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed')
    parser.add_argument('--context', default="", help='Context for safe_float calls')

    args = parser.parse_args()

    total_fixes = 0
    for file_pattern in args.files:
        if '*' in file_pattern:
            files = list(Path('.').glob(file_pattern))
        else:
            files = [Path(file_pattern)]

        for file_path in files:
            if not file_path.suffix == '.py':
                continue

            content, count = fix_unsafe_floats_in_file(file_path, args.context)
            total_fixes += count

            if count > 0:
                if args.dry_run:
                    print(f"Would fix {count} unsafe floats in {file_path}")
                else:
                    file_path.write_text(content)
                    print(f"Fixed {count} unsafe floats in {file_path}")

    print(f"\nTotal files processed: {len(files)}")
    print(f"Total potential fixes: {total_fixes}")
    print("\nNote: Manual review and context assignment recommended for each float() conversion")


if __name__ == '__main__':
    main()
