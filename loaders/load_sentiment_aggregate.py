#!/usr/bin/env python3
"""Sentiment Aggregate Loader - Combines AAII + NAAIM sentiment into unified metric (Market-wide)."""

import logging
import sys
from datetime import date
from typing import List, Optional

from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)

from loaders.loader_helper import setup_imports


setup_imports()


class SentimentAggregateLoader(OptimalLoader):
    """Aggregate AAII and NAAIM sentiment into unified metric."""

    table_name = "sentiment"
    primary_key = ("date",)
    watermark_field = "date"

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Fetch and aggregate sentiment data from AAII and NAAIM."""
        from utils.db.context import DatabaseContext

        try:
            with DatabaseContext("read") as cursor:
                # Get latest AAII bullish reading
                cursor.execute("""
                    SELECT date, bullish
                    FROM aaii_sentiment
                    ORDER BY date DESC LIMIT 1
                """)
                aaii_row = cursor.fetchone()
                aaii_date = aaii_row[0] if aaii_row else None
                aaii_bullish = aaii_row[1] if aaii_row else None

                # Get latest NAAIM allocation reading
                cursor.execute("""
                    SELECT date, bullish_alloc
                    FROM naaim
                    ORDER BY date DESC LIMIT 1
                """)
                naaim_row = cursor.fetchone()
                naaim_date = naaim_row[0] if naaim_row else None
                naaim_bullish = naaim_row[1] if naaim_row else None

                if not aaii_bullish or not naaim_bullish:
                    logger.warning("Missing sentiment data")
                    return None

                # Aggregate: normalized average of both metrics (0-100 scale)
                aggregate_sentiment = (aaii_bullish + naaim_bullish) / 2.0
                record_date = max(aaii_date, naaim_date)

                logger.info(
                    f"Sentiment: AAII={aaii_bullish:.1f}% + NAAIM={naaim_bullish:.1f}% = {aggregate_sentiment:.1f}"
                )

                return [
                    {
                        "date": record_date,
                        "aggregate_sentiment": aggregate_sentiment,
                        "aaii_bullish": aaii_bullish,
                        "naaim_bullish": naaim_bullish,
                    }
                ]

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e


def main():
    try:
        loader = SentimentAggregateLoader()
        result = loader.load_global()

        if result > 0:
            logger.info("SUCCESS: Sentiment aggregate loaded")
            return 0
        else:
            logger.error("FAILED: No sentiment aggregated")
            return 1
    except Exception as e:
        logger.error(f"Sentiment aggregate load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
