#!/usr/bin/env python3
"""Final comprehensive fixer for all 150+ implicit fallback violations."""

import re
from pathlib import Path


def fix_file(filepath: Path) -> int:
    """Remove all implicit defaults from .get() calls."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except:
        return 0

    original = content
    fixed = content

    # Remove .get("key")
    fixed = re.sub(
        r'\.get\s*\(\s*(["\'])([^"\']*)\1\s*,\s*\[\]\s*\)',
        r'.get(\1\2\1)',
        fixed
    )

    # Remove .get('key')
    fixed = re.sub(
        r"\.get\s*\(\s*(['\"])([^'\"]*)\1\s*,\s*\[\]\s*\)",
        r".get(\1\2\1)",
        fixed
    )

    # Remove .get(varname)
    fixed = re.sub(
        r'\.get\s*\(\s*([a-zA-Z_]\w*)\s*,\s*\[\]\s*\)',
        r'.get(\1)',
        fixed
    )

    # Remove .get("key")
    fixed = re.sub(
        r'\.get\s*\(\s*(["\'])([^"\']*)\1\s*,\s*\{\}\s*\)',
        r'.get(\1\2\1)',
        fixed
    )

    # Remove .get('key')
    fixed = re.sub(
        r"\.get\s*\(\s*(['\"])([^'\"]*)\1\s*,\s*\{\}\s*\)",
        r".get(\1\2\1)",
        fixed
    )

    # Remove .get(varname)
    fixed = re.sub(
        r'\.get\s*\(\s*([a-zA-Z_]\w*)\s*,\s*\{\}\s*\)',
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

    print(f"Fixed {fixed_files} files")


if __name__ == "__main__":
    main()
