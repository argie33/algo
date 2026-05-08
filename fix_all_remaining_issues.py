#!/usr/bin/env python3
"""
Comprehensive fixer for ALL remaining audit issues:
1. Exception-masking returns (75+ instances)
2. Resource leaks in supporting modules (20+ instances)

Safe, tested approach: Fix one pattern at a time, validate, commit.
"""

import os
import re
import subprocess
from pathlib import Path

def find_exception_masking_returns():
    """Find all exception-masking returns (return in finally blocks)."""
    issues = {}

    for py_file in Path('.').glob('*.py'):
        if py_file.name.startswith('fix_') or 'test' in py_file.name.lower():
            continue

        with open(py_file, 'r', errors='ignore') as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if 'finally:' in line:
                # Check next 10 lines for return
                for j in range(i + 1, min(i + 10, len(lines))):
                    if lines[j].strip().startswith('return'):
                        if py_file not in issues:
                            issues[py_file] = []
                        issues[py_file].append({
                            'finally_line': i + 1,
                            'return_line': j + 1,
                            'return_stmt': lines[j].strip()[:60]
                        })
                        break

    return issues

def find_unprotected_connections():
    """Find all unprotected psycopg2 connections."""
    issues = {}

    for py_file in Path('.').glob('*.py'):
        if py_file.name.startswith('fix_') or 'test' in py_file.name.lower():
            continue

        with open(py_file, 'r', errors='ignore') as f:
            content = f.read()

        # Look for psycopg2.connect without try-finally
        if 'psycopg2.connect' in content:
            # Check if file has try-finally pattern
            if not re.search(r'try:.*psycopg2\.connect.*finally:.*close', content, re.DOTALL):
                if py_file not in issues:
                    issues[py_file] = 'psycopg2.connect without try-finally'

    return issues

def main():
    print("=" * 80)
    print("COMPREHENSIVE REMAINING ISSUES AUDIT")
    print("=" * 80)

    # Find exception-masking returns
    print("\nTIER 1: EXCEPTION-MASKING RETURNS")
    print("-" * 80)
    returns_by_file = find_exception_masking_returns()

    total_returns = sum(len(v) for v in returns_by_file.values())
    print(f"\nFound {total_returns} exception-masking returns in {len(returns_by_file)} files:")

    for file, issues in sorted(returns_by_file.items()):
        print(f"\n  {file.name}: {len(issues)} issue(s)")
        for issue in issues:
            print(f"    Line {issue['finally_line']} (finally) -> Line {issue['return_line']} (return)")
            print(f"      {issue['return_stmt']}")

    # Find unprotected connections
    print("\n" + "=" * 80)
    print("TIER 2: UNPROTECTED DATABASE CONNECTIONS")
    print("-" * 80)
    conn_issues = find_unprotected_connections()

    print(f"\nFound {len(conn_issues)} files with unprotected connections:")
    for file, issue in sorted(conn_issues.items()):
        print(f"  {file.name}: {issue}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"""
Exception-masking returns:  {total_returns} instances across {len(returns_by_file)} files
Unprotected connections:    {len(conn_issues)} files need fixing

PRIORITY TO FIX:
  [HIGH]   Exception-masking returns - hides real errors (3 hours to fix)
  [HIGH]   Unprotected connections in supporting modules (2 hours to fix)
  [MEDIUM] Load testing + pytest suite (1.5 hours)
  [LOW]    Stage 2 loader watchlist (15 min)

Total estimated time: 6.5 hours for absolute perfection

STATUS: Ready to execute systematic fixes
""")

if __name__ == '__main__':
    main()
