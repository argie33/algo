#!/usr/bin/env python3
"""Fix non-ASCII characters in all Python loader files."""

import os
import re
from pathlib import Path

# Character replacements (using unicode escapes to avoid encoding issues)
REPLACEMENTS = {
    '✓': '[OK]',       # ✓
    '✔': '[OK]',       # ✔
    '✅': '[OK]',       # ✅
    '❌': '[FAIL]',     # ❌
    '✗': '[ERROR]',    # ✗
    '→': ' -> ',       # →
    '←': ' <- ',       # ←
    '≤': '<=',         # ≤
    '≥': '>=',         # ≥
    '≠': '!=',         # ≠
}

def fix_file(filepath):
    """Fix encoding issues in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        original = content
        fixed_any = False

        for unicode_char, replacement in REPLACEMENTS.items():
            if unicode_char in content:
                content = content.replace(unicode_char, replacement)
                fixed_any = True

        if fixed_any and content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        return False

# Find and fix all loader files
loader_dir = Path('loaders')
fixed_count = 0

print("Scanning loaders for encoding issues...\n")

for pyfile in loader_dir.glob('*.py'):
    if fix_file(str(pyfile)):
        print(f"[FIXED] {pyfile.name}")
        fixed_count += 1

print(f"\n[OK] Fixed {fixed_count} files")
