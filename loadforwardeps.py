#!/usr/bin/env python3
"""
Forward EPS Loader - Generate forward estimates from existing earnings history
No external API calls. Uses database data only.
"""

import psycopg2
import os
import logging
import sys
from dotenv import load_dotenv

load_dotenv('.env.local')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'stocks')
    )

def load_forward_eps():
    """Generate forward EPS for all stocks using latest earnings + 12% growth"""
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()

    logging.info("Loading forward EPS from earnings history...")

    # Simple approach: take latest actual EPS, project forward 1 year with 12% growth
    sql = """
    WITH latest_earnings AS (
        SELECT DISTINCT ON (symbol)
            symbol,
            eps_actual,
            earnings_date
        FROM earnings_history
        WHERE eps_actual IS NOT NULL AND eps_actual > 0
        ORDER BY symbol, earnings_date DESC
    ),
    forward_est AS (
        SELECT
            symbol,
            earnings_date + INTERVAL '1 year' as quarter,
            ROUND(CAST(eps_actual * 1.12 AS NUMERIC), 4) as forward_eps
        FROM latest_earnings
    )
    INSERT INTO earnings_estimates (symbol, quarter, eps_estimate)
    SELECT symbol, quarter, forward_eps FROM forward_est
    ON CONFLICT (symbol, quarter) DO UPDATE SET
        eps_estimate = EXCLUDED.eps_estimate
    """

    try:
        cur.execute(sql)
        rows = cur.rowcount
        logging.info(f"[OK] Loaded forward EPS for {rows} stocks")
        return rows
    except Exception as e:
        logging.error(f"Error: {e}")
        return 0
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    load_forward_eps()
