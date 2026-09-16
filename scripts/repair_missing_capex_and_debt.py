#!/usr/bin/env python3
"""Repair missing or clearly-wrong capex and long_term_debt values.

These fields show 0 or negative values when yfinance shows real positive values,
indicating SEC XBRL loader extraction failures (missing facts, wrong concept
selection). Uses yfinance as ground truth to backfill these gaps.

Usage:
    python scripts/repair_missing_capex_and_debt.py --dry-run  # preview
    python scripts/repair_missing_capex_and_debt.py --fix      # apply fixes
"""

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_repair_candidates():
    """Get records with missing/wrong capex or long_term_debt values."""
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("""
      SELECT DISTINCT
        symbol,
        our_table,
        our_field,
        fiscal_year,
        our_value,
        yfinance_value::bigint as correct_value,
        ratio
      FROM xbrl_yfinance_line_item_report
      WHERE divergent = true
        AND our_field IN ('capex', 'long_term_debt')
        AND (our_value IS NULL OR our_value <= 0)
        AND yfinance_value IS NOT NULL
        AND yfinance_value > 0
      ORDER BY our_field, symbol, fiscal_year
    """)

    candidates = cursor.fetchall()
    cursor.close()
    db.close()
    return candidates


def apply_repairs(candidates, dry_run=True):
    """Apply yfinance values to fill missing/wrong capex/debt."""
    db = get_db_connection()
    cursor = db.cursor()

    # Group by symbol/fiscal_year/field
    repairs = {}
    for symbol, table, field, fiscal_year, our_val, correct_value, ratio in candidates:
        key = (symbol, table, fiscal_year, field)
        repairs[key] = (our_val, correct_value, ratio)

    total_records = len(repairs)
    print(f"\n{'=' * 70}")
    print(f"REPAIR PLAN: {total_records} missing/wrong capex/debt values")
    print(f"{'=' * 70}\n")

    # Group by field for summary
    by_field = {}
    for (symbol, _table, _fiscal_year, field), (old_val, new_val, _ratio) in repairs.items():
        if field not in by_field:
            by_field[field] = []
        by_field[field].append((symbol, old_val, new_val))

    for field in sorted(by_field.keys()):
        print(f"{field} ({len(by_field[field])} records):")
        for symbol, old_val, new_val in by_field[field][:5]:
            old_str = f"${old_val:,.0f}" if old_val and old_val != 0 else "NULL/0"
            print(f"  {symbol}: {old_str} -> ${new_val:,.0f}")
        if len(by_field[field]) > 5:
            print(f"  ... and {len(by_field[field]) - 5} more")
        print()

    if dry_run:
        print(f"[DRY-RUN] Would update {total_records} records")
        cursor.close()
        db.close()
        return 0

    # Apply the repairs
    updated_count = 0
    for (symbol, table, fiscal_year, field), (old_val, correct_value, _ratio) in repairs.items():
        cursor.execute(
            f"""
          UPDATE {table}
          SET {field} = %s
          WHERE symbol = %s AND fiscal_year = %s
        """,
            (correct_value, symbol, fiscal_year),
        )

        if cursor.rowcount > 0:
            updated_count += cursor.rowcount
            logger.info(f"Fixed {symbol} FY{fiscal_year} {field}: {old_val} -> {correct_value:,.0f}")

    db.commit()
    print(f"\n[COMPLETED] Updated {updated_count} records\n")

    cursor.close()
    db.close()
    return updated_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--fix", action="store_true", help="Apply repairs to database")
    args = parser.parse_args()

    if not args.dry_run and not args.fix:
        parser.print_help()
        sys.exit(1)

    candidates = get_repair_candidates()
    if not candidates:
        print("No missing/wrong capex/debt records found")
        sys.exit(0)

    dry_run = not args.fix
    updated = apply_repairs(candidates, dry_run=dry_run)

    if updated > 0:
        print(f"Successfully repaired {updated} missing/wrong capex/debt records")


if __name__ == "__main__":
    main()
