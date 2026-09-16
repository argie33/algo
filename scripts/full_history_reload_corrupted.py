#!/usr/bin/env python3
"""Full-history reload for all unreloaded corrupted records.

The incremental loader's watermark tracking missed old fiscal years.
This script does full-history reloads for symbols with unreloaded corruption.
"""

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402


def get_unreloaded_corruptions():
    """Load the corruption audit and find unreloaded records."""
    with open("/tmp/corruption_audit.json") as f:
        corrupted_records = json.load(f)

    severe_moderate = [r for r in corrupted_records if r["ratio"] > 100]

    db = get_db_connection()
    cursor = db.cursor()

    unreloaded = []
    for record in severe_moderate:
        symbol = record["symbol"]
        table = record["table"]
        field = record["field"]
        fiscal_year = record["fiscal_year"]
        corrupted_value_str = str(record["corrupted_value"])

        query = f"SELECT {field} FROM {table} WHERE symbol = %s AND fiscal_year = %s"
        cursor.execute(query, (symbol, fiscal_year))
        result = cursor.fetchone()

        if result:
            current = result[0]
            if str(current) == corrupted_value_str or (
                isinstance(current, (int, float, Decimal)) and float(current) == float(corrupted_value_str)
            ):
                unreloaded.append(
                    {
                        "symbol": symbol,
                        "table": table,
                        "field": field,
                        "fiscal_year": fiscal_year,
                        "corrupted_value": current,
                        "ratio": record["ratio"],
                    }
                )

    cursor.close()
    db.close()

    return unreloaded


def group_by_table_and_symbols(unreloaded):
    """Group unreloaded records by statement table and unique symbols."""
    groups = {}
    for record in unreloaded:
        key = record["table"]
        if key not in groups:
            groups[key] = {"symbols": set(), "count": 0, "records": []}
        groups[key]["symbols"].add(record["symbol"])
        groups[key]["count"] += 1
        groups[key]["records"].append(record)

    return groups


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
        print(f"  Symbols: {len(symbols)}")
        print(f"  Expected records affected: ~{len(symbols) * 10}")
    else:
        print(f"[EXECUTING] {statement_type} for {len(symbols)} symbols...")

        env = os.environ.copy()
        env["LOADER_STATEMENT_TYPE"] = table_to_type[statement_type]
        env["LOADER_PERIOD"] = "annual"
        env["LOADER_BACKFILL_DAYS"] = "3650"

        cmd = ["python3", "scripts/run_loader.py", "load_financial_statements", "--symbols", symbols_str]

        result = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
        return result.returncode == 0

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
    print("FULL-HISTORY RELOAD FOR UNRELOADED CORRUPTIONS")
    print("=" * 80)
    print()

    unreloaded = get_unreloaded_corruptions()
    grouped = group_by_table_and_symbols(unreloaded)

    print(f"Total unreloaded: {sum(g['count'] for g in grouped.values())} records")
    print()

    for table in sorted(grouped.keys()):
        group = grouped[table]
        print(f"{table}:")
        print(f"  Symbols: {len(group['symbols'])}")
        print(f"  Records affected: {group['count']}")
        print()

    dry_run = not args.fix

    for table in sorted(grouped.keys()):
        group = grouped[table]
        execute_reload(table, group["symbols"], dry_run=dry_run)


if __name__ == "__main__":
    main()
