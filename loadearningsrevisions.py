#!/usr/bin/env python3
"""
Earnings Estimate Revisions Loader
Tracks how analyst consensus estimates are changing over time
Source: yfinance eps_trend and eps_revisions
"""
import os
import sys
import logging
from datetime import datetime
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection parameters
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "stocks")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "stocks")

def get_db_connection():
    """Create database connection"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )

def create_tables():
    """Create tables for earnings estimate trends and revisions"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Table for estimate trends (historical snapshots)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS earnings_estimate_trends (
                    symbol VARCHAR(20) NOT NULL,
                    period VARCHAR(10) NOT NULL,
                    snapshot_date DATE NOT NULL,
                    current_estimate NUMERIC,
                    estimate_7d_ago NUMERIC,
                    estimate_30d_ago NUMERIC,
                    estimate_60d_ago NUMERIC,
                    estimate_90d_ago NUMERIC,
                    PRIMARY KEY (symbol, period, snapshot_date)
                );

                CREATE INDEX IF NOT EXISTS idx_estimate_trends_symbol
                    ON earnings_estimate_trends(symbol);
                CREATE INDEX IF NOT EXISTS idx_estimate_trends_date
                    ON earnings_estimate_trends(snapshot_date DESC);
            """)

            # Table for estimate revisions (up/down counts)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS earnings_estimate_revisions (
                    symbol VARCHAR(20) NOT NULL,
                    period VARCHAR(10) NOT NULL,
                    snapshot_date DATE NOT NULL,
                    up_last_7d INTEGER,
                    up_last_30d INTEGER,
                    down_last_7d INTEGER,
                    down_last_30d INTEGER,
                    PRIMARY KEY (symbol, period, snapshot_date)
                );

                CREATE INDEX IF NOT EXISTS idx_estimate_revisions_symbol
                    ON earnings_estimate_revisions(symbol);
                CREATE INDEX IF NOT EXISTS idx_estimate_revisions_date
                    ON earnings_estimate_revisions(snapshot_date DESC);
            """)

            conn.commit()
            logger.info("✓ Tables created/verified")
    finally:
        conn.close()

def fetch_and_load_revisions():
    """Fetch estimate trends and revisions for all symbols"""
    conn = get_db_connection()
    today = datetime.now().date()

    try:
        # Get list of symbols from stock_symbols table
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol IS NOT NULL AND etf = 'N' LIMIT 50")
            symbols = [row[0] for row in cur.fetchall()]

        logger.info(f"Processing {len(symbols)} symbols...")

        trends_data = []
        revisions_data = []
        success_count = 0
        error_count = 0

        for i, symbol in enumerate(symbols, 1):
            try:
                ticker = yf.Ticker(symbol)

                # Get EPS trend data
                eps_trend = ticker.eps_trend
                if eps_trend is not None and not eps_trend.empty:
                    for period in eps_trend.index:
                        row = eps_trend.loc[period]
                        trends_data.append((
                            symbol,
                            str(period),
                            today,
                            float(row.get('current')) if row.get('current') is not None else None,
                            float(row.get('7daysAgo')) if row.get('7daysAgo') is not None else None,
                            float(row.get('30daysAgo')) if row.get('30daysAgo') is not None else None,
                            float(row.get('60daysAgo')) if row.get('60daysAgo') is not None else None,
                            float(row.get('90daysAgo')) if row.get('90daysAgo') is not None else None
                        ))

                # Get EPS revisions data
                eps_revisions = ticker.eps_revisions
                if eps_revisions is not None and not eps_revisions.empty:
                    for period in eps_revisions.index:
                        row = eps_revisions.loc[period]
                        revisions_data.append((
                            symbol,
                            str(period),
                            today,
                            int(row.get('upLast7days', 0)),
                            int(row.get('upLast30days', 0)),
                            int(row.get('downLast7Days', 0)),  # Note: yfinance uses 'Days' not 'days'
                            int(row.get('downLast30days', 0))
                        ))

                success_count += 1
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{len(symbols)} symbols processed")

            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to fetch {symbol}: {e}")
                continue

        # Bulk insert trends data
        if trends_data:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO earnings_estimate_trends
                        (symbol, period, snapshot_date, current_estimate,
                         estimate_7d_ago, estimate_30d_ago, estimate_60d_ago, estimate_90d_ago)
                    VALUES %s
                    ON CONFLICT (symbol, period, snapshot_date)
                    DO UPDATE SET
                        current_estimate = EXCLUDED.current_estimate,
                        estimate_7d_ago = EXCLUDED.estimate_7d_ago,
                        estimate_30d_ago = EXCLUDED.estimate_30d_ago,
                        estimate_60d_ago = EXCLUDED.estimate_60d_ago,
                        estimate_90d_ago = EXCLUDED.estimate_90d_ago
                    """,
                    trends_data
                )
                conn.commit()
                logger.info(f"✓ Loaded {len(trends_data)} estimate trend records")

        # Bulk insert revisions data
        if revisions_data:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO earnings_estimate_revisions
                        (symbol, period, snapshot_date, up_last_7d, up_last_30d,
                         down_last_7d, down_last_30d)
                    VALUES %s
                    ON CONFLICT (symbol, period, snapshot_date)
                    DO UPDATE SET
                        up_last_7d = EXCLUDED.up_last_7d,
                        up_last_30d = EXCLUDED.up_last_30d,
                        down_last_7d = EXCLUDED.down_last_7d,
                        down_last_30d = EXCLUDED.down_last_30d
                    """,
                    revisions_data
                )
                conn.commit()
                logger.info(f"✓ Loaded {len(revisions_data)} estimate revision records")

        logger.info(f"✓ Complete: {success_count} success, {error_count} errors")

    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("Starting earnings estimate revisions loader...")
    create_tables()
    fetch_and_load_revisions()
    logger.info("Done!")
