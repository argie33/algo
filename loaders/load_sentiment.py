#!/usr/bin/env python3
"""Market Sentiment Loader - Load market sentiment from available sources (Market-wide compute)."""

import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

class SentimentLoader(OptimalLoader):
    """Load market sentiment from available sources."""

    table_name = "sentiment"
    primary_key = ("symbol", "date")
    watermark_field = "created_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch market sentiment data."""
        try:
            with DatabaseContext("read") as cur:
                # Get sentiment from aggregated sources
                cur.execute("""
                    SELECT
                        COALESCE(symbol, 'MARKET') AS symbol,
                        MAX(date) as date,
                        AVG(aggregate_sentiment) as sentiment_score,
                        CASE
                            WHEN AVG(aggregate_sentiment) > 65 THEN 'Bullish'
                            WHEN AVG(aggregate_sentiment) > 40 THEN 'Neutral'
                            ELSE 'Bearish'
                        END AS sentiment_label
                    FROM sentiment
                    WHERE created_at > NOW() - INTERVAL '1 day'
                    GROUP BY symbol
                """)

                rows = cur.fetchall()
                if not rows:
                    logger.info("No sentiment data available")
                    return None

                return [
                    {
                        "symbol": r[0],
                        "date": r[1] or date.today(),
                        "sentiment_score": float(r[2]) if r[2] else 0.0,
                        "sentiment_label": r[3],
                    }
                    for r in rows
                ]

        except Exception as e:
            logger.error(f"Failed to fetch sentiment: {e}")
            return None

def main():
    loader = SentimentLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} sentiment records loaded")
        return 0
    else:
        logger.warning("COMPLETED: No sentiment loaded")
        return 0

if __name__ == "__main__":
    sys.exit(main())
