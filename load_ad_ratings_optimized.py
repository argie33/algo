#!/usr/bin/env python3
"""
Load A/D (Accumulation/Distribution) ratings for ALL stocks - Optimized batch version
"""
import psycopg2
import numpy as np
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_HOST = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'
DB_PORT = 5432
DB_USER = 'stocks'
DB_PASSWORD = 'bed0elAn'
DB_NAME = 'stocks'

def get_connection():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME,
        connect_timeout=30
    )

def calculate_ad_rating(cursor, symbol):
    """Calculate A/D rating from price data"""
    try:
        cursor.execute("""
            SELECT date, close, volume
            FROM price_daily
            WHERE symbol = %s
            AND close IS NOT NULL AND volume IS NOT NULL
            ORDER BY date DESC LIMIT 100
        """, (symbol,))

        rows = cursor.fetchall()
        if len(rows) < 20:
            return None

        rows = list(reversed(rows))
        accumulation_volume = 0
        distribution_volume = 0
        total_volume = 0

        for i in range(1, len(rows)):
            current_close = float(rows[i][1])
            current_volume = float(rows[i][2])
            previous_close = float(rows[i-1][1])
            total_volume += current_volume

            if current_close > previous_close:
                accumulation_volume += current_volume
            elif current_close < previous_close:
                distribution_volume += current_volume

        if total_volume == 0:
            return None

        accumulation_pct = (accumulation_volume / total_volume) * 100
        rating_score = 50 + (accumulation_pct / 2)
        return round(rating_score, 2)

    except Exception as e:
        logger.debug(f"Error for {symbol}: {e}")
        return None

def load_all_ad_ratings():
    """Load A/D ratings for all stocks"""
    conn = get_connection()
    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info("LOADING A/D RATINGS FOR ALL STOCKS")
    logger.info("=" * 80)

    # Get all stock symbols
    cur.execute("""
        SELECT DISTINCT symbol FROM stock_symbols
        WHERE exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
        AND (etf = 'N' OR etf IS NULL)
        AND symbol NOT ILIKE '%$%'
        ORDER BY symbol
    """)

    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f"Found {len(symbols)} stocks to process for A/D ratings")

    saved = 0
    skipped = 0

    for i, symbol in enumerate(symbols):
        if (i + 1) % 1000 == 0:
            logger.info(f"Processing {i+1}/{len(symbols)} stocks...")

        ad_rating = calculate_ad_rating(cur, symbol)

        if ad_rating is not None:
            try:
                cur.execute("""
                    UPDATE stock_scores
                    SET ad_rating = %s
                    WHERE symbol = %s
                """, (ad_rating, symbol))

                if cur.rowcount > 0:
                    saved += 1
                else:
                    # Stock not in scores yet, insert placeholder
                    cur.execute("""
                        INSERT INTO stock_scores (symbol, ad_rating, score_date)
                        VALUES (%s, %s, CURRENT_DATE)
                        ON CONFLICT (symbol) DO UPDATE SET ad_rating = EXCLUDED.ad_rating
                    """, (symbol, ad_rating))
                    saved += 1

                if saved % 500 == 0:
                    conn.commit()
                    logger.info(f"  Saved {saved} A/D ratings...")

            except Exception as e:
                logger.warning(f"Error saving {symbol}: {e}")
        else:
            skipped += 1

    conn.commit()
    cur.close()
    conn.close()

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"COMPLETE: Saved {saved} A/D ratings ({skipped} skipped - insufficient data)")
    logger.info("=" * 80)

if __name__ == '__main__':
    load_all_ad_ratings()
