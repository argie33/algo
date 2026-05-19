#!/usr/bin/env python3
"""
Populate sector_ranking from sector_performance data.
Ranks sectors by momentum and creates daily ranking records.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.structured_logger import get_logger
logger = get_logger(__name__)

from utils.optimal_loader import OptimalLoader
from datetime import date
from typing import Optional
import logging

class SectorRankingLoader(OptimalLoader):
    table_name = "sector_ranking"
    primary_key = ("sector_name", "date_recorded")
    watermark_field = "date_recorded"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Generate sector rankings from sector_performance."""
        from utils.db_connection import get_db_connection
        from datetime import timedelta

        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                # Get latest sector performance data and rank by momentum
                # Try today first, fall back to yesterday
                cur.execute("""
                    SELECT sector, date, relative_strength
                    FROM sector_performance
                    WHERE date = (SELECT MAX(date) FROM sector_performance)
                    ORDER BY relative_strength DESC
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.info("No sector_performance data available")
                    return None

                if rows[0][1] != date.today():
                    logger.info(f"Using sector_performance data from {rows[0][1]} (latest available)")
                    date_to_use = rows[0][1]
                else:
                    date_to_use = date.today()

                result = []
                for rank, (sector, data_date, momentum) in enumerate(rows, 1):
                    result.append({
                        "sector_name": sector,
                        "date_recorded": data_date,
                        "current_rank": rank,
                        "momentum_score": float(momentum or 0),
                    })

                return result if result else None

        except Exception as e:
            logger.error(f"Failed to generate sector rankings: {e}")
            return None
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--parallelism', type=int, default=1)
    args = parser.parse_args()

    loader = SectorRankingLoader()
    try:
        loader.run(["sectors"], parallelism=args.parallelism)
    finally:
        loader.close()
