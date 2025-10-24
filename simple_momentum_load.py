#!/usr/bin/env python3
"""
Simple momentum score calculation from price_daily data.
Updates stock_scores.momentum_score directly.
"""

import psycopg2
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        dbname=os.getenv("DB_NAME", "stocks")
    )

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    logging.info("=" * 80)
    logging.info("MOMENTUM SCORE CALCULATION (FROM DATABASE PRICES)")
    logging.info("=" * 80)

    # Calculate momentum for all stocks with sufficient price data
    logging.info("\nCalculating 12-1 month momentum for all stocks...")

    try:
        cur.execute("""
            WITH momentum_data AS (
                SELECT
                    symbol,
                    -- Get current price
                    LAST_VALUE(close) OVER (PARTITION BY symbol ORDER BY date) as current_price,
                    -- Get price 21 days ago (1 month)
                    LAG(close, 21) OVER (PARTITION BY symbol ORDER BY date) as price_1m_ago,
                    -- Get price 252 days ago (12 months)
                    LAG(close, 252) OVER (PARTITION BY symbol ORDER BY date) as price_12m_ago,
                    -- Count records
                    COUNT(*) OVER (PARTITION BY symbol) as data_count,
                    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as row_num
                FROM price_daily
            )
            UPDATE stock_scores ss
            SET momentum_score = ROUND(
                CASE
                    WHEN m.price_12m_ago IS NULL OR m.price_12m_ago = 0 THEN 0.0
                    WHEN m.data_count < 252 THEN 0.0
                    ELSE GREATEST(0, LEAST(100, 50 + ((m.price_1m_ago - m.price_12m_ago) / m.price_12m_ago * 50)))
                END::NUMERIC, 2),
                last_updated = CURRENT_TIMESTAMP
            FROM momentum_data m
            WHERE ss.symbol = m.symbol
            AND m.row_num = 1
        """)

        updated = cur.rowcount
        conn.commit()
        logging.info(f"✅ Updated {updated} momentum scores")

    except Exception as e:
        logging.error(f"❌ Error calculating momentum: {e}")
        conn.rollback()
        sys.exit(1)

    # Verification
    logging.info("\n" + "=" * 80)
    logging.info("VERIFICATION")
    logging.info("=" * 80)

    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN momentum_score > 0 THEN 1 END) as with_score,
            ROUND(AVG(momentum_score)::NUMERIC, 2) as avg_score,
            MIN(momentum_score) as min_score,
            MAX(momentum_score) as max_score
        FROM stock_scores
    """)

    stats = cur.fetchone()
    logging.info(f"Total stocks: {stats[0]:,}")
    logging.info(f"Stocks with momentum > 0: {stats[1]:,}")
    logging.info(f"Average momentum: {stats[2]}")
    logging.info(f"Range: {stats[3]:.2f} - {stats[4]:.2f}")

    # Sample
    cur.execute("""
        SELECT symbol, momentum_score
        FROM stock_scores
        WHERE momentum_score > 0
        ORDER BY momentum_score DESC
        LIMIT 10
    """)

    logging.info("\nTop 10 Stocks by Momentum:")
    for row in cur.fetchall():
        logging.info(f"  {row[0]:<10} {row[1]:>8.2f}")

    cur.close()
    conn.close()

    logging.info("\n✅ MOMENTUM LOADING COMPLETE")

if __name__ == "__main__":
    main()
