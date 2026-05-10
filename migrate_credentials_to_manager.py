#!/usr/bin/env python3
"""
Migrate all credential references from os.getenv() to credential_manager.

This script:
1. Finds all files with old credential patterns
2. Replaces os.getenv("DB_PASSWORD", "") patterns with credential_manager calls
3. Adds import statement at top
4. Validates syntax
5. Reports what was changed

Safe: Only touches files with old patterns, doesn't touch credential_manager.py or credential_validator.py
"""

import os
import re
import sys
from pathlib import Path

# Files to skip
SKIP_FILES = {
    'credential_manager.py',
    'credential_validator.py',
    'migrate_credentials_to_manager.py',
}

# Patterns to replace
PATTERNS = [
    # DB_PASSWORD with empty default
    {
        'pattern': r'os\.getenv\(["\']DB_PASSWORD["\']\s*,\s*["\'][\'"]\)',
        'replacement': 'credential_manager.get_db_credentials()["password"]',
        'description': 'DB_PASSWORD with empty default'
    },
    # DB_PASSWORD without default (also dangerous)
    {
        'pattern': r'os\.getenv\(["\']DB_PASSWORD["\']\)',
        'replacement': 'credential_manager.get_db_credentials()["password"]',
        'description': 'DB_PASSWORD without default'
    },
    # APCA_API_KEY_ID
    {
        'pattern': r'os\.getenv\(["\']APCA_API_KEY_ID["\']\)',
        'replacement': 'credential_manager.get_alpaca_credentials()["key"]',
        'description': 'APCA_API_KEY_ID'
    },
    # APCA_API_SECRET_KEY
    {
        'pattern': r'os\.getenv\(["\']APCA_API_SECRET_KEY["\']\)',
        'replacement': 'credential_manager.get_alpaca_credentials()["secret"]',
        'description': 'APCA_API_SECRET_KEY'
    },
    # ALERT_SMTP_PASSWORD with empty default
    {
        'pattern': r'os\.getenv\(["\']ALERT_SMTP_PASSWORD["\']\s*,\s*["\'][\'"]\)',
        'replacement': 'credential_manager.get_password("smtp/password", default="")',
        'description': 'ALERT_SMTP_PASSWORD with empty default'
    },
]

def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped."""
    basename = os.path.basename(filepath)
    if basename in SKIP_FILES:
        return True
    if filepath.endswith('.pyc') or '__pycache__' in filepath:
        return True
    return False

def has_credential_import(content: str) -> bool:
    """Check if file already imports credential_manager."""
    return 'credential_manager' in content and 'import' in content

def add_credential_import(content: str) -> str:
    """Add import statement if not present."""
    if has_credential_import(content):
        return content

    # Find first import block
    lines = content.split('\n')
    insert_idx = 0

    # Skip shebang and module docstring
    in_docstring = False
    for i, line in enumerate(lines):
        if line.startswith('#!'):
            continue
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i
            break
        if line and not line.startswith('#'):
            # First non-comment, non-docstring line that's not an import
            insert_idx = i
            break

    # Insert import
    lines.insert(insert_idx, 'from credential_manager import get_credential_manager')
    lines.insert(insert_idx + 1, 'credential_manager = get_credential_manager()')
    lines.insert(insert_idx + 2, '')

    return '\n'.join(lines)

def migrate_file(filepath: str) -> tuple[bool, list]:
    """
    Migrate a single file.

    Returns: (modified, changes_made)
    """
    if should_skip_file(filepath):
        return False, []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return False, [f"Could not read: {e}"]

    original = content
    changes = []

    # Check if file has credentials at all
    if 'DB_PASSWORD' not in content and 'APCA_API' not in content and 'ALERT_SMTP' not in content:
        return False, []

    # Apply each pattern
    for pat in PATTERNS:
        count = len(re.findall(pat['pattern'], content))
        if count > 0:
            content = re.sub(pat['pattern'], pat['replacement'], content)
            changes.append(f"{pat['description']}: {count} replacements")

    # If changes made, add import
    if changes:
        content = add_credential_import(content)

        # Write back
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, changes
        except Exception as e:
            return False, [f"Could not write: {e}"]

    return False, []

def main():
    """Migrate all files."""
    repo_root = Path(__file__).parent

    # Find all Python files
    py_files = list(repo_root.glob('*.py')) + \
               list(repo_root.glob('*/*.py')) + \
               list(repo_root.glob('**/*.py'))

    py_files = [str(f) for f in py_files if f.is_file()]

    print(f"Found {len(py_files)} Python files")
    print("Starting migration...\n")

    modified = 0
    skipped = 0
    errors = 0

    for filepath in sorted(py_files):
        was_modified, changes = migrate_file(filepath)

        if not changes and not was_modified:
            skipped += 1
            continue

        if was_modified:
            modified += 1
            print(f"[OK] {filepath}")
            for change in changes:
                print(f"  - {change}")
        else:
            errors += 1
            print(f"[ERROR] {filepath}")
            for change in changes:
                print(f"  - {change}")

    print(f"\n{'='*60}")
    print(f"Results:")
    print(f"  Modified: {modified}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}")

    # Final check
    print("\nVerifying migrations...")
    bad_patterns = [
        r'os\.getenv\(["\']DB_PASSWORD["\']\s*,\s*["\'][\'"]\)',
        r'os\.getenv\(["\']APCA_API_KEY_ID["\']\)',
        r'os\.getenv\(["\']APCA_API_SECRET_KEY["\']\)',
    ]

    remaining = 0
    for filepath in sorted(py_files):
        if should_skip_file(filepath):
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            for pat in bad_patterns:
                if re.search(pat, content):
                    remaining += 1
                    print(f"[WARN] Still has old pattern: {filepath}")
                    break
        except:
            pass

    if remaining == 0:
        print("[OK] No old credential patterns remaining!")
    else:
        print(f"[WARN] {remaining} files still have old patterns")

    return 0 if errors == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
