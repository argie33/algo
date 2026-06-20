#!/usr/bin/env python3
"""Market Sentiment Loader - Aggregate sentiment score from AAII, NAAIM, CNN Fear/Greed.

Run:
    python3 load_sentiment.py
"""

import logging
import sys
from datetime import date

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader
from utils.safe_data_conversion import safe_float


logger = logging.getLogger(__name__)


class SentimentLoader(OptimalLoader):
    """Aggregate market sentiment from AAII, NAAIM, and CNN Fear & Greed."""

    table_name = "sentiment"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Compute a single MARKET sentiment score from available data sources."""
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
                scores.append(safe_float(row[0], default=0.0))

            # AAII sentiment: bullish% as 0-100 score
            cur.execute("""
                SELECT bullish
                FROM aaii_sentiment
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                scores.append(safe_float(row[0], default=0.0))

            # NAAIM exposure index: 0-200 scale → normalize to 0-100
            cur.execute("""
                SELECT naaim_number_mean
                FROM naaim
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row and row[0] is not None:
                scores.append(min(safe_float(row[0], default=0.0) / 2.0, 100.0))

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


if __name__ == "__main__":
    sys.exit(run_loader(SentimentLoader, global_mode=True))
