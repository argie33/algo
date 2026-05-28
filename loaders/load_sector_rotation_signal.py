#!/usr/bin/env python3
"""
Load sector rotation signals from sector_ranking momentum data.
"""
import psycopg2
from datetime import date
import logging
from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)

def load_sector_rotation_signals():
    """Load sector rotation signals based on momentum scores."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get latest sector ranking date
        cur.execute("""
            SELECT MAX(date_recorded) FROM sector_ranking
        """)
        latest_date = cur.fetchone()[0]

        if not latest_date:
            logger.warning("No sector_ranking data found")
            return 0

        # Clear old signals
        cur.execute("""
            DELETE FROM sector_rotation_signal
            WHERE created_at < NOW() - INTERVAL '90 days'
        """)

        # Insert sector rotation signals based on momentum
        cur.execute("""
            INSERT INTO sector_rotation_signal (sector_name, direction, strength, created_at, updated_at)
            SELECT
                sr.sector_name,
                CASE
                    WHEN sr.momentum_score > 0.1 THEN 'up'
                    WHEN sr.momentum_score < -0.1 THEN 'down'
                    ELSE 'neutral'
                END AS direction,
                ABS(sr.momentum_score)::numeric AS strength,
                NOW(),
                NOW()
            FROM (
                SELECT DISTINCT sector_name, momentum_score
                FROM sector_ranking
                WHERE date_recorded = %s
            ) sr
            ON CONFLICT (sector_name) DO UPDATE SET
                direction = EXCLUDED.direction,
                strength = EXCLUDED.strength,
                updated_at = NOW()
        """, (latest_date,))

        inserted = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {inserted} sector rotation signals")
        return inserted

    except Exception as e:
        conn.rollback()
        logger.error(f"Error loading sector rotation signals: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    load_sector_rotation_signals()
