#!/usr/bin/env python3
"""
Add missing UNIQUE constraints for all loaders.
This fixes ON CONFLICT errors across multiple tables.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_manager import get_credential_manager
from config.env_loader import load_env
from utils.db_connection import get_db_connection
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Map of table -> primary key columns
CONSTRAINTS = {
    'sector_performance': ('sector', 'date'),
    'signal_quality_scores': ('symbol', 'date'),
    'swing_trader_scores': ('symbol', 'date'),
    'technical_data_daily': ('symbol', 'date'),
    'trend_template_data': ('symbol', 'date'),
    'annual_income_statement': ('symbol', 'fiscal_year'),
    'quarterly_income_statement': ('symbol', 'fiscal_year', 'fiscal_quarter'),
    'annual_balance_sheet': ('symbol', 'fiscal_year'),
    'quarterly_balance_sheet': ('symbol', 'fiscal_year', 'fiscal_quarter'),
    'annual_cash_flow': ('symbol', 'fiscal_year'),
    'quarterly_cash_flow': ('symbol', 'fiscal_year', 'fiscal_quarter'),
    'earnings_history': ('symbol', 'quarter'),
    'earnings_revisions': ('symbol', 'quarter', 'fiscal_year', 'revision_type'),
    'market_health_daily': ('date',),
    'growth_metrics': ('symbol',),
    'quality_metrics': ('symbol',),
    'value_metrics': ('symbol',),
    'key_metrics': ('symbol',),
}

def add_constraints():
    load_env()
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            for table, cols in CONSTRAINTS.items():
                col_str = ', '.join(cols)
                constraint_name = f"{table}_{col_str.replace(', ', '_')}_unique"

                # Check if table exists
                cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = %s
                )
                """, (table,))

                if not cur.fetchone()[0]:
                    logger.info(f"✗ {table}: table doesn't exist")
                    continue

                # Check if constraint already exists
                cur.execute("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = %s
                AND constraint_type = 'UNIQUE'
                AND (constraint_name LIKE %s OR constraint_name LIKE %s)
                """, (table, f"%{table}%{cols[0]}%", f"%{cols[0]}%{cols[-1]}%"))

                if cur.fetchone():
                    logger.info(f"✓ {table}({col_str}): constraint already exists")
                    continue

                # Check for duplicates
                cur.execute(f"""
                SELECT COUNT(*)
                FROM (
                    SELECT {col_str}, COUNT(*) as cnt
                    FROM {table}
                    GROUP BY {col_str}
                    HAVING COUNT(*) > 1
                ) x
                """)

                dup_count = cur.fetchone()[0]
                if dup_count > 0:
                    logger.warning(f"⚠ {table}({col_str}): found {dup_count} duplicate groups")
                    logger.info(f"  Removing duplicates (keeping max id)...")

                    # Delete all but the latest
                    cur.execute(f"""
                    DELETE FROM {table}
                    WHERE id NOT IN (
                        SELECT MAX(id)
                        FROM {table}
                        GROUP BY {col_str}
                    ) AND id IS NOT NULL
                    """)
                    logger.info(f"  Deleted {cur.rowcount} rows")

                # Add constraint
                try:
                    cur.execute(f"""
                    ALTER TABLE {table}
                    ADD CONSTRAINT {constraint_name}
                    UNIQUE ({col_str})
                    """)
                    logger.info(f"✓ {table}({col_str}): constraint added")
                except Exception as e:
                    if 'already exists' in str(e):
                        logger.info(f"✓ {table}({col_str}): constraint already exists")
                    else:
                        logger.error(f"✗ {table}({col_str}): {e}")
                        conn.rollback()
                        continue

            conn.commit()
            logger.info("\nConstraint migration complete")
            return True

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    success = add_constraints()
    sys.exit(0 if success else 1)
