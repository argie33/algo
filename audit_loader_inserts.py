#!/usr/bin/env python3
"""
Audit all INSERT statements for column mismatches.

Compares INSERT column lists against actual database schema.
Finds bugs like market_exposure (INSERT columns didn't match schema).
"""

import re
import sys
import os
import psycopg2
from pathlib import Path
from typing import Dict, List, Tuple, Set

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

# Load env
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _Path(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

def get_db_connection():
    """Connect to database."""
    password = credential_manager.get_db_credentials()["password"] if credential_manager else os.getenv("DB_PASSWORD", "")
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "stocks"),
        password=password,
        database=os.getenv("DB_NAME", "stocks"),
    )


def get_table_schema(conn, table_name: str) -> Set[str]:
    """Get actual columns in a table from database."""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY column_name
            """, (table_name,))
            return {row[0] for row in cur.fetchall()}
    except Exception as e:
        return set()


def extract_inserts_from_file(filepath: str) -> List[Tuple[str, str, List[str]]]:
    """Extract INSERT statements from a Python file.

    Returns: [(table_name, full_sql, [column_list]), ...]
    """
    with open(filepath, 'r') as f:
        content = f.read()

    # Match: INSERT INTO table_name (col1, col2, ...) VALUES
    pattern = r'INSERT\s+INTO\s+(\w+)\s*\(([^)]+)\)'
    matches = re.finditer(pattern, content, re.IGNORECASE)

    results = []
    for match in matches:
        table_name = match.group(1)
        cols_str = match.group(2)
        columns = [c.strip() for c in cols_str.split(',')]
        results.append((table_name, match.group(0), columns))

    return results


def main():
    """Audit all loaders for schema mismatches."""
    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"❌ Cannot connect to database: {e}")
        return 1

    issues = []

    # Scan all Python files
    root = Path(".")
    for pyfile in sorted(root.glob("*.py")):
        if "__pycache__" in str(pyfile):
            continue

        # Only check loader and algo files
        if not ("load" in pyfile.name or "algo_" in pyfile.name):
            continue

        inserts = extract_inserts_from_file(str(pyfile))

        for table_name, sql_snippet, columns in inserts:
            schema_cols = get_table_schema(conn, table_name)

            if not schema_cols:
                # Table doesn't exist - might be OK (new table) or might be typo
                issues.append({
                    'file': pyfile.name,
                    'severity': 'WARN',
                    'issue': f"Table '{table_name}' not found in database",
                    'columns_used': columns,
                })
                continue

            # Check for column mismatches
            columns_set = set(columns)
            missing = columns_set - schema_cols

            if missing:
                issues.append({
                    'file': pyfile.name,
                    'severity': 'ERROR',
                    'issue': f"INSERT into '{table_name}' uses columns that don't exist in schema",
                    'columns_used': columns,
                    'missing_columns': list(missing),
                    'schema_has': sorted(schema_cols),
                })

    conn.close()

    # Report findings
    if not issues:
        print("✓ No INSERT column mismatches found!")
        return 0

    print(f"\n🔍 Found {len(issues)} potential issues:\n")

    for issue in sorted(issues, key=lambda x: x['severity'], reverse=True):
        if issue['severity'] == 'ERROR':
            print(f"❌ {issue['file']}")
            print(f"   Table: {issue['issue']}")
            print(f"   Missing columns: {', '.join(issue.get('missing_columns', []))}")
            print()
        elif issue['severity'] == 'WARN':
            print(f"⚠️  {issue['file']}")
            print(f"   {issue['issue']}")
            print()

    error_count = sum(1 for x in issues if x['severity'] == 'ERROR')
    return 1 if error_count > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
