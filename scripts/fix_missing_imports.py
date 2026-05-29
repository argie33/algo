#!/usr/bin/env python3
"""Fix files that call get_db_connection() but don't import it."""

import re
from pathlib import Path

def fix_file(filepath):
    """Add get_db_connection import if missing but used."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Check if file uses get_db_connection but doesn't import it
    has_call = 'get_db_connection()' in content
    has_import = 'get_db_connection' in content and 'import' in content

    if not has_call or has_import:
        return False

    # Find and update DatabaseContext import to include get_db_connection
    content = re.sub(
        r'(from utils\.database_context import DatabaseContext)(?!.*get_db_connection)',
        r'\1, get_db_connection',
        content
    )

    if 'get_db_connection' in content and 'import' in content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True

    return False

algo_root = Path(__file__).parent.parent
fixed = 0

for py_file in algo_root.rglob('*.py'):
    if 'migrate' in str(py_file) or 'fix_missing' in str(py_file):
        continue
    try:
        if fix_file(py_file):
            print(f"Fixed: {py_file.relative_to(algo_root)}")
            fixed += 1
    except Exception as e:
        print(f"Error: {py_file.relative_to(algo_root)}: {e}")

print(f"\nFixed {fixed} files")
