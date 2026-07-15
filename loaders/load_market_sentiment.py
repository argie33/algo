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
        # Do NOT silently fallback to 20.0 - this corrupts risk controls (investors think VIX is known when it's not)
        if not row or row["vix_level"] is None:
            logger.error(
                f"[CRITICAL] VIX data missing for {today} - cannot compute market sentiment. "
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

        # Bull/bear/neutral percentages come from the AAII weekly investor survey
        # (aaii_sentiment table). The survey is weekly, so accept the latest row up
        # to 14 days old (one missed week of slack). If no fresh survey exists,
        # these fields are NULL - never fabricated. (This loader previously wrote a
        # hardcoded 33.33/33.33/33.34 split with data_unavailable=False, presenting
        # invented neutrality as real survey data.)
        sentiment_score: Decimal | None = None
        bullish_pct: Decimal | None = None
        bearish_pct: Decimal | None = None
        neutral_pct: Decimal | None = None
        reason: str | None = None
        cur.execute(
            """
            SELECT date, bullish, bearish, neutral FROM aaii_sentiment
            WHERE date >= %s - INTERVAL '14 days'
              AND bullish IS NOT NULL AND bearish IS NOT NULL AND neutral IS NOT NULL
            ORDER BY date DESC LIMIT 1
            """,
            (today,),
        )
        aaii = cur.fetchone()
        if aaii is not None:
            # aaii_sentiment stores bullish/bearish/neutral as fractions (0-1), not percentages
            aaii_bullish = float(aaii["bullish"])
            aaii_bearish = float(aaii["bearish"])
            aaii_neutral = float(aaii["neutral"])
            total = aaii_bullish + aaii_bearish + aaii_neutral
            if 0.95 <= total <= 1.05:
                bullish_pct = Decimal(str(round(aaii_bullish * 100, 4)))
                bearish_pct = Decimal(str(round(aaii_bearish * 100, 4)))
                neutral_pct = Decimal(str(round(aaii_neutral * 100, 4)))
                # Standard bull-bear spread normalization onto a 0-100 scale:
                # all-bullish -> 100, all-bearish -> 0, balanced -> 50.
                spread_score = 50.0 + (aaii_bullish - aaii_bearish) * 50.0
                sentiment_score = Decimal(str(round(max(0.0, min(100.0, spread_score)), 4)))
            else:
                reason = "aaii_survey_percentages_invalid"
                logger.error(
                    f"[DATA_QUALITY] aaii_sentiment row {aaii['date']} fractions sum to {total:.4f} "
                    "(expected ~1.0) - refusing to publish invalid survey data"
                )
        else:
            reason = "aaii_survey_data_unavailable"
            logger.warning(
                f"No AAII survey data within 14 days of {today} - "
                "bullish/bearish/neutral published as NULL (fear/greed from VIX still real)"
            )

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
                False,  # fear/greed (the row's primary metric) is real VIX-derived data
                reason,  # notes partial unavailability when AAII fields are NULL
            ),
        )

        logger.info(
            f"Market sentiment loader completed for {today}: fear_greed={fear_greed} "
            f"sentiment_score={sentiment_score} (aaii={'present' if bullish_pct is not None else 'unavailable'})"
        )


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
