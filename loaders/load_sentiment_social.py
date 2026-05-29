#!/usr/bin/env python3
"""
Load social media sentiment data (Twitter, Reddit, StockTwits).
Currently uses placeholder data pending external API integration.
"""
import psycopg2
from datetime import datetime, date
import logging
from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)

def load_sentiment_social():
    """Load social media sentiment from sources or use calculated metrics."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        latest_price_date = None
        cur.execute("SELECT MAX(date) FROM price_daily")
        result = cur.fetchone()
        if result:
            latest_price_date = result[0]

        if not latest_price_date:
            logger.warning("No price data to reference for sentiment dates")
            return 0

        # Clear old sentiment data
        cur.execute("""
            DELETE FROM sentiment_social
            WHERE created_at < NOW() - INTERVAL '90 days'
        """)

        # Calculate sentiment from market psychology indicators where available
        # For symbols without direct social data, derive from price action and technical signals
        cur.execute("""
            INSERT INTO sentiment_social (
                symbol, date, twitter_sentiment_score, twitter_mention_count,
                reddit_sentiment_score, reddit_mention_count,
                stocktwits_sentiment_score, stocktwits_mention_count,
                overall_sentiment_score, sentiment_trend, source_count,
                sentiment_breakdown, created_at, updated_at
            )
            SELECT
                pd.symbol,
                pd.date,
                COALESCE(
                    CASE WHEN roc.roc_252d > 0 THEN 0.5 + (roc.roc_252d / 200.0) ELSE 0.5 + (roc.roc_252d / 200.0) END,
                    0.5
                )::numeric AS twitter_sentiment_score,
                50::integer AS twitter_mention_count,
                COALESCE(
                    CASE WHEN roc.roc_60d > 0 THEN 0.5 + (roc.roc_60d / 100.0) ELSE 0.5 + (roc.roc_60d / 100.0) END,
                    0.5
                )::numeric AS reddit_sentiment_score,
                25::integer AS reddit_mention_count,
                COALESCE(
                    CASE WHEN roc.roc_20d > 0 THEN 0.5 + (roc.roc_20d / 50.0) ELSE 0.5 + (roc.roc_20d / 50.0) END,
                    0.5
                )::numeric AS stocktwits_sentiment_score,
                30::integer AS stocktwits_mention_count,
                COALESCE(
                    (CASE WHEN roc.roc_252d > 0 THEN 0.5 + (roc.roc_252d / 200.0) ELSE 0.5 + (roc.roc_252d / 200.0) END +
                     CASE WHEN roc.roc_60d > 0 THEN 0.5 + (roc.roc_60d / 100.0) ELSE 0.5 + (roc.roc_60d / 100.0) END +
                     CASE WHEN roc.roc_20d > 0 THEN 0.5 + (roc.roc_20d / 50.0) ELSE 0.5 + (roc.roc_20d / 50.0) END) / 3.0,
                    0.5
                )::numeric AS overall_sentiment_score,
                CASE
                    WHEN roc.roc_20d > 5 THEN 'strong_bullish'
                    WHEN roc.roc_20d > 2 THEN 'bullish'
                    WHEN roc.roc_20d < -5 THEN 'strong_bearish'
                    WHEN roc.roc_20d < -2 THEN 'bearish'
                    ELSE 'neutral'
                END::text AS sentiment_trend,
                3::integer AS source_count,
                '{"source":"technical"}'::jsonb AS sentiment_breakdown,
                NOW(),
                NOW()
            FROM (
                SELECT DISTINCT symbol, date FROM price_daily
                WHERE date = %s
                LIMIT 500
            ) pd
            LEFT JOIN technical_data_daily roc ON roc.symbol = pd.symbol AND roc.date = pd.date
            ON CONFLICT (symbol, date) DO UPDATE SET
                overall_sentiment_score = EXCLUDED.overall_sentiment_score,
                sentiment_trend = EXCLUDED.sentiment_trend,
                updated_at = NOW()
        """, (latest_price_date,))

        inserted = cur.rowcount
        conn.commit()
        logger.info(f"Loaded {inserted} social sentiment records (placeholder data)")
        return inserted

    except Exception as e:
        conn.rollback()
        logger.error(f"Error loading social sentiment: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    load_sentiment_social()
