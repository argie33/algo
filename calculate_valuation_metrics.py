#!/usr/bin/env python3
"""
Calculate valuation metrics (P/E, P/B, etc) from existing price and financial data
"""

import psycopg2
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USER", "stocks"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

def calculate_pe_ratios():
    """Calculate P/E ratios from latest price and EPS data"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Calculate P/E from latest price and EPS
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price, date
                FROM price_daily
                ORDER BY symbol, date DESC
            ),
            with_pe AS (
                SELECT
                    km.ticker as symbol,
                    lp.price,
                    km.eps_trailing,
                    CASE
                        WHEN km.eps_trailing > 0 AND km.eps_trailing IS NOT NULL
                        THEN lp.price / km.eps_trailing
                        ELSE NULL
                    END as calculated_pe
                FROM key_metrics km
                JOIN latest_price lp ON km.ticker = lp.symbol
                WHERE km.eps_trailing IS NOT NULL AND km.eps_trailing > 0
            )
            SELECT COUNT(*) FROM with_pe WHERE calculated_pe IS NOT NULL;
        """)

        count = cur.fetchone()[0]
        logger.info(f"Can calculate P/E for {count} stocks")

        # Insert calculated P/E into value_metrics
        cur.execute("""
            WITH latest_price AS (
                SELECT DISTINCT ON (symbol) symbol, close as price, date
                FROM price_daily
                ORDER BY symbol, date DESC
            )
            INSERT INTO value_metrics (symbol, date, trailing_pe)
            SELECT
                km.ticker,
                CURRENT_DATE,
                CASE
                    WHEN km.eps_trailing > 0 AND km.eps_trailing IS NOT NULL
                    THEN lp.price / km.eps_trailing
                    ELSE NULL
                END
            FROM key_metrics km
            JOIN latest_price lp ON km.ticker = lp.symbol
            ON CONFLICT (symbol, date) DO UPDATE SET
                trailing_pe = EXCLUDED.trailing_pe
            WHERE EXCLUDED.trailing_pe IS NOT NULL;
        """, vars={'pd': 'price_daily'})

        conn.commit()
        logger.info(f"✅ Updated P/E ratios in value_metrics")

    except Exception as e:
        logger.error(f"Error: {str(e)[:200]}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    calculate_pe_ratios()
