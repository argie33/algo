#!/usr/bin/env python3
"""
Batch migrate all get_db_connection() calls to DatabaseContext.

This handles:
1. Import statements
2. Simple get_db_connection() calls (context manager pattern)
3. Connections passed to classes (extract via cur.connection)
"""

import re
import sys
from pathlib import Path

def migrate_file(filepath):
    """Migrate a single file to DatabaseContext."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # 1. Replace import
    content = re.sub(
        r'from utils\.db_connection import get_db_connection',
        'from utils.database_context import DatabaseContext',
        content
    )

    # 2. Handle simple patterns: conn = get_db_connection()
    # Pattern: conn = get_db_connection() followed by cur = conn.cursor()
    content = re.sub(
        r'(\s+)conn = get_db_connection\(\)\n(\s+)cur = conn\.cursor\(\)',
        r'\1with DatabaseContext() as cur:',
        content
    )

    # 3. Handle: db_conn = get_db_connection() passed to classes
    # Will need manual review, but we can mark them
    if 'db_conn = get_db_connection()' in content:
        content = re.sub(
            r'(\s+)db_conn = get_db_connection\(\)',
            r'\1with DatabaseContext() as cur:\n\1    db_conn = cur.connection',
            content
        )

    # 4. Remove manual close calls that are now handled by context manager
    # But be careful - only remove if inside a with block

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    algo_root = Path(__file__).parent.parent

    # Find all files that import get_db_connection
    files_to_migrate = []

    for py_file in algo_root.rglob('*.py'):
        if 'migrate_db_connections' in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding='utf-8')
            if 'from utils.db_connection import get_db_connection' in content:
                files_to_migrate.append(py_file)
        except Exception as e:
            pass  # Skip files with encoding issues

    print(f"Found {len(files_to_migrate)} files to migrate")

    migrated = 0
    for filepath in files_to_migrate:
        try:
            if migrate_file(filepath):
                print(f"OK {filepath.relative_to(algo_root)}")
                migrated += 1
            else:
                print(f"   {filepath.relative_to(algo_root)} (no changes)")
        except Exception as e:
            print(f"ERR {filepath.relative_to(algo_root)}: {e}")

    print(f"\nMigrated {migrated}/{len(files_to_migrate)} files")
    return 0 if migrated == len(files_to_migrate) else 1

if __name__ == '__main__':
    sys.exit(main())
