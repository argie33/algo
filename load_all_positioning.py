#!/usr/bin/env python3
"""
Load positioning metrics for ALL stocks from yfinance
"""
import psycopg2
import yfinance as yf
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

def load_all_positioning():
    """Load positioning metrics for all stocks"""
    conn = get_connection()
    cur = conn.cursor()

    logger.info("=" * 80)
    logger.info("LOADING POSITIONING METRICS FOR ALL STOCKS")
    logger.info("=" * 80)

    # Get all stock symbols
    cur.execute("""
        SELECT DISTINCT symbol FROM stock_symbols
        WHERE exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
        AND (etf = 'N' OR etf IS NULL)
        AND (test_issue != 'Y' OR test_issue IS NULL)
        AND symbol NOT ILIKE '%$%'
        ORDER BY symbol
    """)

    symbols = [row[0] for row in cur.fetchall()]
    logger.info(f"Found {len(symbols)} eligible stocks to process")

    saved = 0
    errors = 0

    for i, symbol in enumerate(symbols):
        if (i + 1) % 500 == 0:
            logger.info(f"Processing {i+1}/{len(symbols)} stocks...")

        try:
            # Get stock info from yfinance
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Extract positioning metrics
            institutional_ownership = info.get('heldPercentInstitutions', None)
            insider_ownership = info.get('heldPercentInsiders', None)
            short_interest = info.get('shortPercentOfFloat', None)
            institution_count = info.get('institutionOwned', None)

            # Save to database
            cur.execute("""
                INSERT INTO positioning_metrics (
                    symbol, institutional_ownership_pct, insider_ownership_pct,
                    short_interest_pct, institutional_holders_count, date
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    institutional_ownership_pct = EXCLUDED.institutional_ownership_pct,
                    insider_ownership_pct = EXCLUDED.insider_ownership_pct,
                    short_interest_pct = EXCLUDED.short_interest_pct,
                    institutional_holders_count = EXCLUDED.institutional_holders_count
            """, (symbol, institutional_ownership, insider_ownership, short_interest, institution_count))

            saved += 1

            if saved % 500 == 0:
                conn.commit()
                logger.info(f"  Saved {saved} stocks")

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"Error for {symbol}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"COMPLETE: Saved {saved} positioning records ({errors} errors)")
    logger.info("=" * 80)

if __name__ == '__main__':
    load_all_positioning()
