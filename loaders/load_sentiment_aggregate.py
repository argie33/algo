#!/usr/bin/env python3
"""Sentiment Aggregate Loader â€" combines AAII + NAAIM sentiment into unified metric.

Aggregates multiple sentiment sources (AAII bullish %, NAAIM allocation %) into a
normalized sentiment score (0-100, where 50 = neutral) for trading signals.

Run: python3 load_sentiment_aggregate.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta
from typing import Optional

import logging
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

def load_sentiment_aggregate():
    """Aggregate AAII and NAAIM sentiment into unified table."""

    with DatabaseContext() as cursor:
        try:
            # Get the latest AAII bullish reading
            cursor.execute("""
                SELECT date, bullish_pct, neutral_pct, bearish_pct
                FROM aaii_sentiment
                ORDER BY date DESC LIMIT 1
            """)
            aaii_row = cursor.fetchone()
            aaii_date = aaii_row[0] if aaii_row else None
            aaii_bullish = aaii_row[1] if aaii_row else None

            # Get the latest NAAIM allocation reading
            cursor.execute("""
                SELECT date, bullish_alloc, neutral_alloc, bearish_alloc
                FROM naaim
                ORDER BY date DESC LIMIT 1
            """)
            naaim_row = cursor.fetchone()
            naaim_date = naaim_row[0] if naaim_row else None
            naaim_bullish = naaim_row[1] if naaim_row else None

            if not aaii_bullish or not naaim_bullish:
                logger.warning("Missing sentiment data: AAII=%s, NAAIM=%s", aaii_bullish, naaim_bullish)
                return 0

            # Ensure both dates are recent (within 7 days)
            today = date.today()
            if aaii_date < today - timedelta(days=7):
                logger.warning("AAII sentiment stale: %s (>7 days old)", aaii_date)
            if naaim_date < today - timedelta(days=7):
                logger.warning("NAAIM sentiment stale: %s (>7 days old)", naaim_date)

            # Aggregate: normalized average of both metrics (0-100 scale)
            # AAII bullish % is already 0-100
            # NAAIM bullish_alloc is already 0-100
            aggregate_sentiment = (aaii_bullish + naaim_bullish) / 2.0

            # Sentiment interpretation:
            # 0-25: Extreme bearish
            # 25-40: Bearish
            # 40-60: Neutral
            # 60-75: Bullish
            # 75-100: Extreme bullish

            record_date = max(aaii_date, naaim_date)

            logger.info(
                f"Sentiment aggregate: AAII={aaii_bullish:.1f}% + NAAIM={naaim_bullish:.1f}% = {aggregate_sentiment:.1f}"
            )

            # Insert into sentiment table
            cursor.execute("""
                INSERT INTO sentiment (date, aggregate_sentiment, aaii_bullish, naaim_bullish, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (date) DO UPDATE SET
                    aggregate_sentiment = %s,
                    aaii_bullish = %s,
                    naaim_bullish = %s,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                record_date, aggregate_sentiment, aaii_bullish, naaim_bullish,
                aggregate_sentiment, aaii_bullish, naaim_bullish
            ))

            logger.info("Sentiment aggregate load completed")
            return 1

        except Exception as e:
            logger.error(f"Sentiment aggregation failed: {e}", exc_info=True)
            return 0

def main():
    try:
        result = load_sentiment_aggregate()
        return 0 if result > 0 else 1
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())

