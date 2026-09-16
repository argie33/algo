#!/usr/bin/env python3
"""Repair moderate-severe scale errors (50-100x divergence).

Fixes records where values diverge 50-100x from yfinance cross-check data.
These are clearly corrupt (unit/scale conversion errors), not plausible reporting differences.

Usage:
    python scripts/repair_moderate_50_100x_errors.py --dry-run  # preview
    python scripts/repair_moderate_50_100x_errors.py --fix      # apply fixes
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
    """Get records with 50-100x divergences."""
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("""
      SELECT DISTINCT
        symbol,
        our_table,
        our_field,
        fiscal_year,
        yfinance_value::bigint as correct_value,
        ratio
      FROM xbrl_yfinance_line_item_report
      WHERE divergent = true AND ratio > 50 AND ratio <= 100
      ORDER BY ratio DESC, symbol, fiscal_year
    """)

    candidates = cursor.fetchall()
    cursor.close()
    db.close()
    return candidates


def apply_repairs(candidates, dry_run=True):
    """Apply yfinance values to correct the fields."""
    db = get_db_connection()
    cursor = db.cursor()

    # Group by symbol/fiscal_year/field
    repairs = {}
    for symbol, table, field, fiscal_year, correct_value, ratio in candidates:
        key = (symbol, table, fiscal_year, field)
        repairs[key] = (correct_value, ratio)

    total_records = len(repairs)
    print(f"\n{'=' * 70}")
    print(f"REPAIR PLAN: {total_records} moderate-severe records (50-100x divergence)")
    print(f"{'=' * 70}\n")

    # Preview the changes
    preview_count = 0
    for (symbol, table, fiscal_year, field), (correct_value, ratio) in sorted(repairs.items()):
        if preview_count < 15:
            # Get current value for preview
            cursor.execute(
                f"""
              SELECT {field} FROM {table}
              WHERE symbol = %s AND fiscal_year = %s
            """,
                (symbol, fiscal_year),
            )
            result = cursor.fetchone()
            if result:
                current_value = result[0]
                print(
                    f"  {symbol:6s} FY{fiscal_year} {field:30s}: "
                    f"{current_value:15,.0f} -> {correct_value:15,.0f} ({ratio:.0f}x error)"
                )
            preview_count += 1

    if preview_count < total_records:
        print(f"  ... and {total_records - preview_count} more\n")

    if dry_run:
        print(f"[DRY-RUN] Would update {total_records} records")
        cursor.close()
        db.close()
        return 0

    # Apply the repairs
    updated_count = 0
    for (symbol, table, fiscal_year, field), (correct_value, ratio) in repairs.items():
        cursor.execute(
            f"""
          UPDATE {table}
          SET {field} = %s
          WHERE symbol = %s AND fiscal_year = %s AND {field} IS NOT NULL
        """,
            (correct_value, symbol, fiscal_year),
        )

        if cursor.rowcount > 0:
            updated_count += cursor.rowcount
            logger.info(f"Fixed {symbol} FY{fiscal_year} {field}: {ratio:.0f}x error corrected")

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
        print("No moderate-severe records found (50-100x divergence)")
        sys.exit(0)

    dry_run = not args.fix
    updated = apply_repairs(candidates, dry_run=dry_run)

    if updated > 0:
        print(f"Successfully repaired {updated} moderate-severe records")


if __name__ == "__main__":
    main()
