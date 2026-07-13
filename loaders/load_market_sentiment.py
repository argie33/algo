#!/usr/bin/env python3
"""Market Sentiment Loader - Computes fear/greed and market sentiment indicators.

Runs daily to populate market_sentiment table with current market sentiment metrics.
Uses VIX to compute fear/greed index.
"""

import logging
from datetime import datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)


def compute_market_sentiment() -> None:
    today = datetime.now(EASTERN_TZ).date()

    with DatabaseContext("write", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # Get VIX level from market_health_daily - use most recent available data (may not have today yet)
        # This handles intra-day scenarios where market_health_daily is still being loaded
        cur.execute(
            "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
            (today,),
        )
        row = cur.fetchone()

        # CRITICAL DATA QUALITY GATE: Fail-fast if VIX data missing
        # Do NOT silently fallback to 20.0 — this corrupts risk controls (investors think VIX is known when it's not)
        if not row or row["vix_level"] is None:
            logger.error(
                f"[CRITICAL] VIX data missing for {today} — cannot compute market sentiment. "
                "Risk assessment requires current VIX level. Aborting market sentiment update."
            )
            # Upsert data_unavailable flag instead of computing with fallback
            cur.execute(
                """
                INSERT INTO market_sentiment (
                    date, fear_greed_index, sentiment_score, bullish_pct, bearish_pct, neutral_pct,
                    data_unavailable, reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    fear_greed_index = EXCLUDED.fear_greed_index,
                    sentiment_score = EXCLUDED.sentiment_score,
                    bullish_pct = EXCLUDED.bullish_pct,
                    bearish_pct = EXCLUDED.bearish_pct,
                    neutral_pct = EXCLUDED.neutral_pct,
                    data_unavailable = EXCLUDED.data_unavailable,
                    reason = EXCLUDED.reason
            """,
                (
                    today,
                    None,  # No fear_greed index available
                    None,  # No sentiment score
                    None,
                    None,
                    None,
                    True,  # Mark as unavailable
                    "vix_data_missing",  # Explicit reason for data unavailability
                ),
            )
            logger.info(f"Market sentiment marked data_unavailable for {today}: vix_data_missing")
            return

        vix = float(row["vix_level"])

        # Map VIX to fear/greed index: VIX 10-50 → fear/greed 80-20
        # VIX 10 = greed (80), VIX 50 = fear (20), VIX 20 = neutral (50)
        fear_greed = max(10, min(90, 100 - (vix * 2)))

        # Upsert into market_sentiment with data quality flags
        sentiment_score = Decimal("50.0000")  # Neutral sentiment (50% = neutral between greed/fear)
        bullish_pct = Decimal("33.3333")
        bearish_pct = Decimal("33.3333")
        neutral_pct = Decimal("33.3334")

        cur.execute(
            """
            INSERT INTO market_sentiment (
                date, fear_greed_index, sentiment_score, bullish_pct, bearish_pct, neutral_pct,
                data_unavailable, reason
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date) DO UPDATE SET
                fear_greed_index = EXCLUDED.fear_greed_index,
                sentiment_score = EXCLUDED.sentiment_score,
                bullish_pct = EXCLUDED.bullish_pct,
                bearish_pct = EXCLUDED.bearish_pct,
                neutral_pct = EXCLUDED.neutral_pct,
                data_unavailable = EXCLUDED.data_unavailable,
                reason = EXCLUDED.reason
        """,
            (
                today,
                Decimal(str(round(fear_greed, 4))),
                sentiment_score,
                bullish_pct,
                bearish_pct,
                neutral_pct,
                False,  # Data is available
                None,  # No unavailability reason
            ),
        )

        logger.info(f"Market sentiment loader completed for {today}: fear_greed={fear_greed}")


def main() -> None:
    """Main entry point for the loader."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        compute_market_sentiment()
    except Exception as e:
        logger.error(f"Market sentiment loader failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
