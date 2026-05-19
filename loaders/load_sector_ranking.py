#!/usr/bin/env python3
"""
Populate sector_ranking from sector_performance data.
Ranks sectors by momentum and creates daily ranking records.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Generate and insert sector rankings."""
    from utils.db_connection import get_db_connection

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Get latest sector performance data and rank by momentum
            cur.execute("""
                SELECT sector, date, relative_strength
                FROM sector_performance
                WHERE date = (SELECT MAX(date) FROM sector_performance)
                ORDER BY relative_strength DESC
            """)

            rows = cur.fetchall()
            if not rows:
                logger.info("No sector_performance data available")
                return 0

            data_date = rows[0][1]
            logger.info(f"Using sector_performance data from {data_date}")

            # Delete existing data for this date (idempotent)
            cur.execute("DELETE FROM sector_ranking WHERE date_recorded = %s", (data_date,))

            # Insert rankings
            for rank, (sector, _, momentum) in enumerate(rows, 1):
                cur.execute("""
                    INSERT INTO sector_ranking
                    (sector_name, date_recorded, current_rank, momentum_score)
                    VALUES (%s, %s, %s, %s)
                """, (sector, data_date, rank, float(momentum or 0)))

            conn.commit()
            logger.info(f"Inserted {len(rows)} sector rankings for {data_date}")
            return 0

    except Exception as e:
        logger.error(f"Failed to generate sector rankings: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return 1
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

if __name__ == "__main__":
    sys.exit(main())
