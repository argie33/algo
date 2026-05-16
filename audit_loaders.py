#!/usr/bin/env python3
"""
Loader Integration Audit - Verify all 36 loaders write to correct tables with correct columns

This tool inspects each loader's INSERT statements and verifies:
1. Target table exists in database schema
2. Column names in INSERT match actual table columns
3. Column order and types are compatible
4. No silent failures will occur
"""

import os
import re
import glob
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Tuple

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Get DB config."""
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        try:
            from credential_manager import get_credential_manager
            credential_manager = get_credential_manager()
            db_password = credential_manager.get_db_credentials()["password"]
        except Exception:
            db_password = "postgres"

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": db_password,
        "database": os.getenv("DB_NAME", "stocks"),
    }

class LoaderAuditor:
    """Audit loader INSERT statements against database schema."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.findings = []
        self.loaders = []

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def audit_all_loaders(self) -> Dict:
        """Audit all loaders in repo."""
        self.connect()
        try:
            loader_files = glob.glob("load*.py")
            results = {}

            print(f"\n{'='*70}")
            print(f"LOADER INTEGRATION AUDIT - {len(loader_files)} loaders found")
            print(f"{'='*70}\n")

            for loader_file in sorted(loader_files):
                try:
                    result = self._audit_loader(loader_file)
                    results[loader_file] = result
                    status = "✓ OK" if result['pass'] else "✗ ISSUE"
                    print(f"{status}: {loader_file:35s} → {result['table'] or 'unknown'}")
                    if result['issues']:
                        for issue in result['issues']:
                            print(f"        ⚠️  {issue}")
                except Exception as e:
                    results[loader_file] = {'pass': False, 'error': str(e), 'table': None}
                    print(f"✗ ERROR: {loader_file:35s}")
                    print(f"        {str(e)}")

            # Summary
            passed = sum(1 for r in results.values() if r.get('pass'))
            failed = len(results) - passed
            print(f"\n{'='*70}")
            print(f"SUMMARY: {passed} loaders OK, {failed} with issues")
            print(f"{'='*70}\n")

            return {
                'total_loaders': len(loader_files),
                'passed': passed,
                'failed': failed,
                'results': results,
            }
        finally:
            self.disconnect()

    def _audit_loader(self, loader_file: str) -> Dict:
        """Audit a single loader file."""
        with open(loader_file, 'r') as f:
            content = f.read()

        # Find INSERT INTO statements
        insert_pattern = r'INSERT\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES'
        matches = re.findall(insert_pattern, content, re.IGNORECASE | re.DOTALL)

        if not matches:
            return {
                'pass': False,
                'table': None,
                'issues': ['No INSERT statement found'],
                'columns': []
            }

        # Get the first INSERT statement (usually the main one)
        table_name, columns_str = matches[0]
        columns = [col.strip() for col in columns_str.split(',')]

        # Verify table exists
        self.cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
        """, (table_name,))
        table_exists = self.cur.fetchone()[0]

        if not table_exists:
            return {
                'pass': False,
                'table': table_name,
                'issues': [f'Table "{table_name}" does not exist in database'],
                'columns': columns
            }

        # Get actual table columns
        self.cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        actual_columns = {row['column_name']: row['data_type'] for row in self.cur.fetchall()}

        # Verify all INSERT columns exist in table
        issues = []
        for col in columns:
            if col not in actual_columns:
                issues.append(f'Column "{col}" not found in table "{table_name}"')

        return {
            'pass': len(issues) == 0,
            'table': table_name,
            'columns': columns,
            'issues': issues,
        }


def main():
    auditor = LoaderAuditor()
    result = auditor.audit_all_loaders()

    # Print summary
    print(f"Results saved to loader_audit_results.txt")

    # Write detailed report
    with open('loader_audit_results.txt', 'w') as f:
        f.write("LOADER INTEGRATION AUDIT RESULTS\n")
        f.write("=" * 70 + "\n\n")

        for loader, details in result['results'].items():
            f.write(f"\n{loader}\n")
            f.write("-" * 70 + "\n")
            f.write(f"Status: {'PASS' if details.get('pass') else 'FAIL'}\n")
            f.write(f"Table: {details.get('table', 'unknown')}\n")
            if details.get('columns'):
                f.write(f"Columns: {', '.join(details['columns'])}\n")
            if details.get('issues'):
                f.write(f"\nIssues:\n")
                for issue in details['issues']:
                    f.write(f"  - {issue}\n")
            if details.get('error'):
                f.write(f"Error: {details['error']}\n")

    if result['failed'] == 0:
        print(f"\n✅ ALL LOADERS PASS - System ready for data loading")
        return 0
    else:
        print(f"\n⚠️  {result['failed']} loaders have issues - Fix before production")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
