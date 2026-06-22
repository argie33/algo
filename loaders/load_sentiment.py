#!/usr/bin/env python3
"""Market Sentiment Loader - Aggregate sentiment score from AAII, NAAIM, CNN Fear/Greed.

Run:
    python3 load_sentiment.py
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.loaders import fetch_latest
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class SentimentLoader(OptimalLoader):
    """Aggregate market sentiment from AAII, NAAIM, and CNN Fear & Greed."""

    table_name = "sentiment"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        """Compute a single MARKET sentiment score from available data sources."""
        scores = []

        # CNN Fear & Greed: scale 0-100 → already 0-100
        row = fetch_latest("fear_greed_index", "date")
        if row and row.get("fear_greed_value") is not None:
            scores.append(float(row["fear_greed_value"]))

        # AAII sentiment: bullish% as 0-100 score
        row = fetch_latest("aaii_sentiment", "date")
        if row and row.get("bullish") is not None:
            scores.append(float(row["bullish"]))

        # NAAIM exposure index: 0-200 scale → normalize to 0-100
        row = fetch_latest("naaim", "date")
        if row and row.get("naaim_number_mean") is not None:
            scores.append(min(float(row["naaim_number_mean"]) / 2.0, 100.0))

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
