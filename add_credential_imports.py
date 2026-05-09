#!/usr/bin/env python3
"""Add credential_manager imports to all files that use it."""

import os
import re
from pathlib import Path

def add_import_if_missing(filepath):
    """Add credential_manager import if file uses it but doesn't import it."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except:
        return False

    # If doesn't use credential_manager, skip
    if 'credential_manager' not in content:
        return False

    # If already imports it, skip
    if re.search(r'(from credential_manager|import credential_manager)', content):
        return False

    # Find insert location (after imports, after shebang/docstring)
    lines = content.split('\n')
    insert_idx = 0
    in_docstring = False

    for i, line in enumerate(lines):
        # Skip shebang
        if line.startswith('#!'):
            insert_idx = i + 1
            continue

        # Skip module docstring
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
            if in_docstring:
                insert_idx = i + 1
            continue

        if in_docstring:
            insert_idx = i + 1
            continue

        # Found first import or code
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i
            break

        if line and not line.startswith('#'):
            # Hit code before imports, insert before it
            insert_idx = i
            break

    # Insert import
    lines.insert(insert_idx, 'from credential_manager import get_credential_manager')
    lines.insert(insert_idx + 1, 'credential_manager = get_credential_manager()')
    lines.insert(insert_idx + 2, '')

    # Write back
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return True
    except:
        return False

# Find all files
repo_root = Path(__file__).parent
py_files = list(repo_root.glob('*.py')) + list(repo_root.glob('*/*.py')) + list(repo_root.glob('**/*.py'))

count = 0
for f in sorted(py_files):
    if f.is_file() and add_import_if_missing(str(f)):
        count += 1
        print(f"Added import to: {f.name}")

print(f"\nAdded imports to {count} files")
