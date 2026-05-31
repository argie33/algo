#!/usr/bin/env python3
"""Industry Ranking Loader - Rank industries by performance metrics (Market-wide)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)


class IndustryRankingLoader(OptimalLoader):
    """Rank industries by performance metrics."""

    table_name = "industry_ranking"
    primary_key = ("industry", "date")
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute industry rankings from stock performance data."""
        try:
            with DatabaseContext('read') as cur:
                # Get latest price date
                cur.execute("SELECT MAX(date) FROM price_daily")
                latest_date = cur.fetchone()[0]

                if not latest_date:
                    return None

                # Rank industries by average stock performance
                cur.execute("""
                    SELECT
                        f.industry,
                        %s::date as date,
                        COUNT(DISTINCT p.symbol) as stock_count,
                        AVG(CASE WHEN p.close > 0 AND p.open > 0
                            THEN (p.close - p.open) / p.open * 100
                            ELSE NULL
                        END) as avg_daily_return,
                        RANK() OVER (ORDER BY AVG(CASE
                            WHEN p.close > 0 AND p.open > 0
                            THEN (p.close - p.open) / p.open * 100
                            ELSE NULL
                        END) DESC) as industry_rank
                    FROM price_daily p
                    LEFT JOIN stock_fundamentals f ON p.symbol = f.symbol
                    WHERE p.date = %s AND f.industry IS NOT NULL
                    GROUP BY f.industry
                    ORDER BY industry_rank
                """, (latest_date, latest_date))

                rows = cur.fetchall()
                if not rows:
                    return None

                return [
                    {
                        'industry': r[0],
                        'date': r[1],
                        'stock_count': r[2],
                        'avg_daily_return': float(r[3]) if r[3] else None,
                        'industry_rank': r[4],
                    }
                    for r in rows
                ]

        except Exception as e:
            logger.error(f"Failed to compute industry rankings: {e}")
            return None


def main():
    loader = IndustryRankingLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} industries ranked")
        return 0
    else:
        logger.warning(f"COMPLETED: No rankings computed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
