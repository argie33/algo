#!/usr/bin/env python3
"""
Load market sentiment data from available sources (AAII, market_sentiment, fear_greed_index).
"""
import psycopg2
from datetime import datetime
import logging
from utils.db_connection import get_db_connection

logger = logging.getLogger(__name__)

def load_sentiment():
    """Load market sentiment from available sources."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Clear old sentiment data (keep last 90 days)
        cur.execute("""
            DELETE FROM sentiment
            WHERE created_at < NOW() - INTERVAL '90 days'
        """)

        # Insert sentiment from AAII data (if available)
        cur.execute("""
            INSERT INTO sentiment (symbol, sentiment_score, sentiment_label, created_at, updated_at)
            SELECT
                COALESCE(symbol, 'MARKET') AS symbol,
                CASE
                    WHEN bullish = true THEN 0.5
                    WHEN neutral = true THEN 0.0
                    ELSE -0.5
                END AS sentiment_score,
                CASE
                    WHEN bullish = true THEN 'Bullish'
                    WHEN neutral = true THEN 'Neutral'
                    ELSE 'Bearish'
                END AS sentiment_label,
                NOW(),
                NOW()
            FROM aaii_sentiment
            WHERE created_at > NOW() - INTERVAL '1 day'
            ON CONFLICT (symbol) DO UPDATE SET
                sentiment_score = EXCLUDED.sentiment_score,
                sentiment_label = EXCLUDED.sentiment_label,
                updated_at = NOW()
        """)

        inserted = cur.rowcount

        # If no AAII data, insert neutral market sentiment
        if inserted == 0:
            cur.execute("""
                INSERT INTO sentiment (symbol, sentiment_score, sentiment_label, created_at, updated_at)
                VALUES ('MARKET', 0.0, 'Neutral', NOW(), NOW())
                ON CONFLICT (symbol) DO NOTHING
            """)
            inserted = cur.rowcount

        conn.commit()
        logger.info(f"Loaded {inserted} sentiment records")
        return inserted

    except Exception as e:
        conn.rollback()
        logger.error(f"Error loading sentiment: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    load_sentiment()
