#!/usr/bin/env python3
"""
Load sector data from sector_ranking and S&P 500 data.
Populates the sectors table with performance metrics.
"""
import psycopg2
from datetime import date, datetime, timedelta
import logging
from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)

def load_sectors():
    """Load sector master data."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get latest sector ranking data
        cur.execute("""
            SELECT MAX(date_recorded) FROM sector_ranking
        """)
        latest_date = cur.fetchone()[0]

        if not latest_date:
            logger.warning("No sector_ranking data found")
            return 0

        # Get S&P 500 symbols count by sector from stock_symbols
        # We'll use sector_ranking as the source since stock_symbols doesn't have sector

        # Insert sector performance data from latest sector_ranking data
        cur.execute("""
            INSERT INTO sector_performance (sector, date, return_pct, relative_strength, created_at)
            SELECT
                sr.sector_name AS sector,
                %s::date AS date,
                COALESCE(sr.momentum_score, 0)::numeric AS return_pct,
                COALESCE(sr.momentum_score, 0)::numeric AS relative_strength,
                NOW()
            FROM (
                SELECT DISTINCT sector_name, momentum_score
                FROM sector_ranking
                WHERE date_recorded = %s
            ) sr
            ON CONFLICT (sector, date) DO UPDATE SET
                return_pct = EXCLUDED.return_pct,
                relative_strength = EXCLUDED.relative_strength
        """, (latest_date, latest_date))

        inserted = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {inserted} sectors")
        return inserted

    except Exception as e:
        conn.rollback()
        logger.error(f"Error loading sectors: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    load_sectors()
