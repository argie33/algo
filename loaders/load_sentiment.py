#!/usr/bin/env python3
"""Market Sentiment Loader - Aggregate sentiment score from AAII, NAAIM, CNN Fear/Greed."""

import sys
import logging
from datetime import date
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class SentimentLoader(OptimalLoader):
    """Aggregate market sentiment from AAII, NAAIM, and CNN Fear & Greed."""

    table_name = "sentiment"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute a single MARKET sentiment score from available data sources."""
        try:
            with DatabaseContext("read") as cur:
                scores = []

                # CNN Fear & Greed: scale 0-100 → already 0-100
                cur.execute("""
                    SELECT fear_greed_value
                    FROM fear_greed_index
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    scores.append(float(row[0]))

                # AAII sentiment: bullish% as 0-100 score
                cur.execute("""
                    SELECT bullish
                    FROM aaii_sentiment
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    scores.append(float(row[0]))

                # NAAIM exposure index: 0-200 scale → normalize to 0-100
                cur.execute("""
                    SELECT naaim_number_mean
                    FROM naaim
                    ORDER BY date DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if row and row[0] is not None:
                    scores.append(min(float(row[0]) / 2.0, 100.0))

                if not scores:
                    logger.info("No sentiment source data available")
                    return None

                avg_score = sum(scores) / len(scores)
                if avg_score > 65:
                    label = "Bullish"
                elif avg_score > 40:
                    label = "Neutral"
                else:
                    label = "Bearish"

                return [
                    {
                        "symbol": "MARKET",
                        "sentiment_score": round(avg_score, 4),
                        "sentiment_label": label,
                    }
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
