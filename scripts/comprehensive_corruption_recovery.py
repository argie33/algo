#!/usr/bin/env python3
"""Comprehensive recovery for ALL 1,063 corrupted records from SEC XBRL source.

This script reloads the complete financial history for all symbols with corrupted records,
ensuring every corrupted record is restored to SEC-authoritative data.
"""

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def get_all_corrupted_symbols():
    """Load corruption audit and extract all unique symbols."""
    with open("/tmp/corruption_audit.json") as f:
        corrupted_records = json.load(f)

    symbols_by_table = defaultdict(set)
    for record in corrupted_records:
        table = record["table"]
        symbol = record["symbol"]
        symbols_by_table[table].add(symbol)

    return symbols_by_table


def execute_reload(statement_type, symbols, dry_run=True):
    """Execute full-history loader for a statement type and symbols."""
    import os

    table_to_type = {
        "annual_income_statement": "income",
        "annual_balance_sheet": "balance",
        "annual_cash_flow": "cashflow",
    }

    symbols_str = ",".join(sorted(symbols))

    if dry_run:
        print("[DRY-RUN] Would execute:")
        print(f"  Statement Type: {statement_type}")
        print(f"  Symbols: {len(symbols)} ({', '.join(sorted(symbols)[:5])}{'...' if len(symbols) > 5 else ''})")
        print(f"  Expected records affected: ~{len(symbols) * 10}")
    else:
        print(f"[EXECUTING] Reloading {statement_type} for {len(symbols)} symbols...")
        print(f"  Symbols: {', '.join(sorted(symbols)[:10])}{'...' if len(symbols) > 10 else ''}")

        env = os.environ.copy()
        env["LOADER_STATEMENT_TYPE"] = table_to_type[statement_type]
        env["LOADER_PERIOD"] = "annual"
        env["LOADER_BACKFILL_DAYS"] = "3650"

        cmd = ["python3", "scripts/run_loader.py", "load_financial_statements", "--symbols", symbols_str]

        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, env=env)
        if result.returncode == 0:
            print("  [OK] Success")
            return True
        else:
            print("  [FAILED] Failed")
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}")
            return False

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--fix", action="store_true", help="Execute reloads")
    args = parser.parse_args()

    if not args.dry_run and not args.fix:
        parser.print_help()
        sys.exit(1)

    print("=" * 80)
    print("COMPREHENSIVE CORRUPTION RECOVERY - RELOAD ALL 1,063 CORRUPTED RECORDS")
    print("=" * 80)
    print()

    symbols_by_table = get_all_corrupted_symbols()
    total_corrupted = sum(len(syms) for syms in symbols_by_table.values())

    print(f"Total corrupted symbols: {total_corrupted}")
    print()

    for table in sorted(symbols_by_table.keys()):
        symbols = symbols_by_table[table]
        print(f"{table}: {len(symbols)} symbols")

    print()

    dry_run = not args.fix
    all_success = True

    for table in sorted(symbols_by_table.keys()):
        symbols = symbols_by_table[table]
        success = execute_reload(table, symbols, dry_run=dry_run)
        all_success = all_success and success

    print()
    if dry_run:
        print("[DRY-RUN COMPLETE] Review above and run with --fix to execute")
    else:
        if all_success:
            print("[RECOVERY COMPLETE] All corrupted records reloaded from SEC source")
        else:
            print("[RECOVERY PARTIAL] Some reloads failed - review errors above")


if __name__ == "__main__":
    main()
