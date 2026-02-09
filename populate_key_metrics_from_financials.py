#!/usr/bin/env python3
"""
Populate key_metrics from existing annual_income_statement data
This fills in missing financial data WITHOUT yfinance API calls
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

def populate_key_metrics():
    """Populate key_metrics from annual_income_statement"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    try:
        # Get latest financial data per stock
        cur.execute("""
            WITH latest_year AS (
                SELECT symbol, MAX(date) as latest_date
                FROM annual_income_statement
                GROUP BY symbol
            )
            SELECT ais.symbol, ais.revenue, ais.net_income, ais.eps
            FROM annual_income_statement ais
            JOIN latest_year ly ON ais.symbol = ly.symbol AND ais.date = ly.latest_date
        """)

        records = cur.fetchall()
        logger.info(f"Found {len(records)} stocks with financial data")

        # Insert into key_metrics (or update if exists)
        inserted = 0
        for symbol, revenue, net_income, eps in records:
            try:
                cur.execute("""
                    INSERT INTO key_metrics (ticker, total_revenue, net_income, eps_trailing)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (ticker) DO UPDATE SET
                        total_revenue = EXCLUDED.total_revenue,
                        net_income = EXCLUDED.net_income,
                        eps_trailing = EXCLUDED.eps_trailing
                """, (symbol, revenue, net_income, eps))
                inserted += 1

                if inserted % 500 == 0:
                    logger.info(f"  ✓ Inserted {inserted} records...")
                    conn.commit()

            except Exception as e:
                logger.error(f"Error inserting {symbol}: {str(e)[:100]}")
                conn.rollback()
                continue

        conn.commit()
        logger.info(f"✅ Successfully populated {inserted} key_metrics from financial statements")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    populate_key_metrics()
