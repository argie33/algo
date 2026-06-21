#!/usr/bin/env python3
"""Fix remaining complex patterns not caught by simple regex."""

import re
from pathlib import Path


def fix_file(filepath: Path) -> int:
    """Fix remaining violations with complex patterns."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except:
        return 0

    original = content
    fixed = content

    # Pattern: .get(anything) where anything is complex (contains [ or other special chars)
    # Use negative lookahead to avoid matching things we already fixed
    # Match: .get(stuff) where stuff is non-trivial
    fixed = re.sub(
        r'\.get\s*\(\s*([^,)]+?)\s*,\s*\[\]\s*\)',
        r'.get(\1)',
        fixed
    )

    # Match: .get(stuff) where stuff is non-trivial
    fixed = re.sub(
        r'\.get\s*\(\s*([^,)]+?)\s*,\s*\{\}\s*\)',
        r'.get(\1)',
        fixed
    )

    if fixed != original:
        try:
            filepath.write_text(fixed, encoding='utf-8')
            return 1
        except:
            return 0

    return 0


def main():
    root = Path(".")
    fixed_files = 0

    for py_file in sorted(root.rglob("*.py")):
        if any(skip in py_file.parts for skip in ['.venv', '__pycache__', '.git']):
            continue

        if fix_file(py_file):
            fixed_files += 1
            print(f"  {py_file.relative_to(root)}")

    print(f"\nFixed {fixed_files} files")


if __name__ == "__main__":
    main()
