#!/usr/bin/env python3
"""
Add missing UNIQUE constraint to sector_performance table.
This fixes the "ON CONFLICT" error in the sectors loader.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.credential_manager import get_credential_manager
from config.env_loader import load_env
from utils.db_connection import get_db_connection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_constraint():
    load_env()
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Check if constraint already exists
            cur.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_name = 'sector_performance'
            AND constraint_type = 'UNIQUE'
            AND constraint_name LIKE '%sector%date%'
            """)

            if cur.fetchone():
                logger.info("UNIQUE constraint on (sector, date) already exists")
                return True

            # Check for duplicate (sector, date) pairs
            cur.execute("""
            SELECT sector, date, COUNT(*) as cnt
            FROM sector_performance
            GROUP BY sector, date
            HAVING COUNT(*) > 1
            """)

            duplicates = cur.fetchall()
            if duplicates:
                logger.warning(f"Found {len(duplicates)} duplicate (sector, date) pairs:")
                for sector, date, cnt in duplicates:
                    logger.warning(f"  {sector} {date}: {cnt} rows")
                logger.info("Removing duplicates (keeping most recent)...")

                # Keep only the most recent row for each (sector, date)
                cur.execute("""
                DELETE FROM sector_performance
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM sector_performance
                    GROUP BY sector, date
                )
                """)
                logger.info(f"Deleted {cur.rowcount} duplicate rows")

            # Add the constraint
            cur.execute("""
            ALTER TABLE sector_performance
            ADD CONSTRAINT sector_performance_sector_date_unique
            UNIQUE (sector, date)
            """)

            conn.commit()
            logger.info("Successfully added UNIQUE constraint on (sector, date)")
            return True

    except Exception as e:
        logger.error(f"Error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    success = add_constraint()
    sys.exit(0 if success else 1)
