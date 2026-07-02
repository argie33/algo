#!/usr/bin/env python3
"""
Quick diagnostic: Check if migration 0044 is applied to AWS RDS.
If not, apply it immediately.

Usage:
    python3 scripts/check_and_fix_migration_0044.py
"""

import sys
import logging

sys.path.insert(0, '.')

from utils.db.context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def check_schema():
    """Check if quality_score and debt_to_assets columns exist."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'quality_metrics'
                  AND column_name IN ('quality_score', 'debt_to_assets')
                ORDER BY column_name
            """)
            columns = [row[0] for row in cur.fetchall()]
            return columns
    except Exception as e:
        logger.error(f"Schema check failed: {e}")
        return None


def apply_migration():
    """Apply migration 0044 to add missing columns."""
    migrations = [
        # Core score columns
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quality_score DECIMAL(5, 2);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets DECIMAL(8, 4);",
        # Unavailable reason columns
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS operating_margin_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS net_margin_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roe_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS roa_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_equity_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS current_ratio_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS quick_ratio_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS interest_coverage_unavailable_reason VARCHAR(255);",
        "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS debt_to_assets_unavailable_reason VARCHAR(255);",
        # Performance index
        "CREATE INDEX IF NOT EXISTS idx_quality_metrics_quality_score ON quality_metrics(quality_score DESC);",
    ]

    try:
        with DatabaseContext("write") as cur:
            for sql in migrations:
                cur.execute(sql)
                logger.info(f"[OK] {' '.join(sql.split()[0:4])}")
            logger.info("[OK] Migration 0044 applied successfully!")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def verify_data_flow():
    """Verify financial data is starting to flow."""
    try:
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as with_score
                FROM quality_metrics
                LIMIT 1
            """)
            total, with_score = cur.fetchone()
            logger.info(f"Quality metrics: {total} rows, {with_score} with scores")
            return True
    except Exception as e:
        logger.error(f"Data flow check failed: {e}")
        return False


def main():
    print("\n" + "="*80)
    print("MIGRATION 0044 DIAGNOSTIC CHECK")
    print("="*80 + "\n")

    # Step 1: Check schema
    print("STEP 1: Checking schema...")
    columns = check_schema()

    if columns is None:
        logger.error("Cannot connect to database. Check credentials.")
        return 1

    if len(columns) == 2:
        print(f"[OK] Migration 0044 ALREADY APPLIED")
        print(f"   Columns present: {', '.join(columns)}\n")
        verify_data_flow()
        return 0
    else:
        print(f"[FAIL] Migration 0044 NOT APPLIED")
        print(f"   Missing columns: quality_score, debt_to_assets\n")

        # Step 2: Apply migration
        print("STEP 2: Applying migration 0044...")
        if apply_migration():
            print("\n[OK] Migration applied successfully!")
            print("   Financial data will flow on next pipeline run.\n")
            verify_data_flow()
            return 0
        else:
            print("\n[FAIL] Migration failed. Check database credentials.\n")
            return 1


if __name__ == "__main__":
    sys.exit(main())
