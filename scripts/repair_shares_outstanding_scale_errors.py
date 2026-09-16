#!/usr/bin/env python3
"""Repair severely-corrupt shares_outstanding values using yfinance cross-check data.

This script fixes the shares_outstanding_basic/diluted fields where our SEC-derived
values diverge from yfinance by >100x (26 symbols, typically caused by SEC XBRL
scale/unit conversion bugs). These are clearly wrong and need immediate correction.

The xbrl_yfinance_line_item_report table (from scripts/xbrl_yfinance_crosscheck.py)
provides the yfinance-independent validation we trust as ground truth for these fixes.

Usage:
    python scripts/repair_shares_outstanding_scale_errors.py --dry-run  # preview
    python scripts/repair_shares_outstanding_scale_errors.py --fix      # apply fixes
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
    """Get symbols with shares_outstanding divergences > 100x (severely corrupt)."""
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("""
      SELECT DISTINCT
        symbol,
        our_field,
        fiscal_year,
        yfinance_value::bigint as correct_value,
        ratio
      FROM xbrl_yfinance_line_item_report
      WHERE divergent = true
        AND our_field IN ('shares_outstanding_basic', 'shares_outstanding_diluted')
        AND ratio > 100
      ORDER BY ratio DESC, symbol, fiscal_year
    """)

    candidates = cursor.fetchall()
    cursor.close()
    db.close()
    return candidates


def apply_repairs(candidates, dry_run=True):
    """Apply yfinance values to correct the shares_outstanding fields."""
    db = get_db_connection()
    cursor = db.cursor()

    # Group by symbol/fiscal_year/field for efficient bulk updates
    repairs = {}
    for symbol, field, fiscal_year, correct_value, ratio in candidates:
        key = (symbol, fiscal_year, field)
        repairs[key] = (correct_value, ratio)

    total_records = len(repairs)
    print(f"\n{'=' * 70}")
    print(f"REPAIR PLAN: {total_records} severely-corrupt records (>100x divergence)")
    print(f"{'=' * 70}\n")

    # Preview the changes
    preview_count = 0
    for (symbol, fiscal_year, field), (correct_value, ratio) in sorted(repairs.items()):
        if preview_count < 10:
            # Get current value for preview
            cursor.execute(
                f"""
              SELECT {field} FROM annual_income_statement
              WHERE symbol = %s AND fiscal_year = %s
            """,
                (symbol, fiscal_year),
            )
            result = cursor.fetchone()
            if result:
                current_value = result[0]
                print(
                    f"  {symbol:6s} FY{fiscal_year} {field:30s}: "
                    f"{current_value:20,} -> {correct_value:20,} ({ratio:.0f}x error)"
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
    for (symbol, fiscal_year, field), (correct_value, ratio) in repairs.items():
        cursor.execute(
            f"""
          UPDATE annual_income_statement
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
        print("No severely-corrupt records found (>100x divergence)")
        sys.exit(0)

    dry_run = not args.fix
    updated = apply_repairs(candidates, dry_run=dry_run)

    if updated > 0:
        print(f"Successfully repaired {updated} shares_outstanding records")


if __name__ == "__main__":
    main()
