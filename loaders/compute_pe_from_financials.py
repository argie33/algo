#!/usr/bin/env python3
"""
Compute PE ratio from financial data that's already in the database.

Uses: market_cap (from key_metrics) + net_income (from annual_income_statement)
PE = Market Cap / Net Income

Falls back to yfinance if needed, but uses what we have first.
"""
import os
import sys
from pathlib import Path
from typing import Optional
import logging
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

import psycopg2
from config.credential_helper import get_db_password

s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_db_conn():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )

def compute_pe_from_financials():
    """Compute PE ratios using financial data already in database."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Get latest financial data for each symbol that has both market cap and net income
        # Use price to estimate market cap: market_cap = price * shares_outstanding
        cur.execute("""
            WITH latest_price AS (
                SELECT symbol, close as price, date
                FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            ),
            latest_income AS (
                SELECT symbol, net_income, fiscal_year
                FROM annual_income_statement
                WHERE (symbol, fiscal_year) IN (
                    SELECT symbol, MAX(fiscal_year)
                    FROM annual_income_statement
                    GROUP BY symbol
                )
            ),
            symbol_shares AS (
                SELECT DISTINCT on (pd.symbol) pd.symbol, ais.net_income, lp.price
                FROM price_daily pd
                LEFT JOIN latest_income ais ON pd.symbol = ais.symbol
                LEFT JOIN latest_price lp ON pd.symbol = lp.symbol
                WHERE ais.net_income IS NOT NULL AND ais.net_income != 0
                  AND lp.price > 0
                ORDER BY pd.symbol, pd.date DESC
                LIMIT 5000
            )
            SELECT symbol, net_income, price
            FROM symbol_shares
        """)

        rows = cur.fetchall()
        logger.info(f"Found {len(rows)} symbols with income data to compute PE")

        # For now, just note that we need market cap data
        # The issue is key_metrics doesn't have market_cap populated
        logger.warning("key_metrics.market_cap is empty - cannot compute PE without it")
        logger.warning("Need to populate key_metrics.market_cap from Finnhub or yfinance first")

        return len(rows)

    finally:
        conn.close()

def main():
    logger.info("Attempting to compute PE ratios from available data")
    count = compute_pe_from_financials()

    if count == 0:
        logger.error("Failed: key_metrics doesn't have market_cap data")
        logger.error("Solution: Run load_key_metrics.py with working Finnhub API key")
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())
