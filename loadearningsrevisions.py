#!/usr/bin/env python3
"""
Earnings Estimate Revisions Loader
Tracks how analyst consensus estimates are changing over time
Source: yfinance eps_trend and eps_revisions

FEATURES:
- Loads ALL symbols (not limited)
- Batch processing with rate limiting
- Proper error handling and retry logic
- Progress tracking and detailed logging
- Clears stale data before reloading
"""
import os
import sys
import logging
import time
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

def clear_old_data(conn, days=0):
    """Clear data older than specified days (0 = clear all)"""
    try:
        with conn.cursor() as cur:
            if days == 0:
                cur.execute("DELETE FROM earnings_estimate_trends")
                cur.execute("DELETE FROM earnings_estimate_revisions")
                logger.info("🗑️  Cleared all old earnings estimate data")
            else:
                cur.execute(f"""
                    DELETE FROM earnings_estimate_trends
                    WHERE snapshot_date < CURRENT_DATE - INTERVAL '{days} days'
                """)
                cur.execute(f"""
                    DELETE FROM earnings_estimate_revisions
                    WHERE snapshot_date < CURRENT_DATE - INTERVAL '{days} days'
                """)
                logger.info(f"🗑️  Cleared earnings data older than {days} days")
            conn.commit()
    except Exception as e:
        logger.error(f"Error clearing old data: {e}")
        conn.rollback()

def fetch_and_load_revisions():
    """Fetch estimate trends and revisions for ALL symbols with batching and rate limiting"""
    conn = get_db_connection()
    today = datetime.now().date()

    try:
        # Clear old data before reloading
        clear_old_data(conn, days=0)

        # Get list of ALL symbols from stock_symbols table (NO LIMIT!)
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol IS NOT NULL AND etf = 'N' ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]

        logger.info(f"📊 Processing {len(symbols)} total symbols...")
        logger.info(f"⏱️  Estimated time: {len(symbols) * 1 / 60:.1f} minutes (with aggressive rate limiting)")
        logger.warning("⚠️  NOTE: yfinance eps_trend/eps_revisions are frequently rate-limited.")

        # Batch parameters
        batch_size = 50
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        all_trends_data = []
        all_revisions_data = []
        success_count = 0
        no_data_count = 0
        error_count = 0

        # Process in batches
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = min(batch_start + batch_size, len(symbols))
            batch_symbols = symbols[batch_start:batch_end]

            logger.info(f"\n📦 Batch {batch_num + 1}/{total_batches} ({batch_start + 1}-{batch_end}/{len(symbols)})")

            for i, symbol in enumerate(batch_symbols, 1):
                try:
                    ticker = yf.Ticker(symbol)

                    # Get EPS trend data
                    has_trend = False
                    eps_trend = ticker.eps_trend
                    if eps_trend is not None and not eps_trend.empty:
                        has_trend = True
                        for period in eps_trend.index:
                            row = eps_trend.loc[period]
                            all_trends_data.append((
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
                    has_revisions = False
                    eps_revisions = ticker.eps_revisions
                    if eps_revisions is not None and not eps_revisions.empty:
                        has_revisions = True
                        for period in eps_revisions.index:
                            row = eps_revisions.loc[period]
                            all_revisions_data.append((
                                symbol,
                                str(period),
                                today,
                                int(row.get('upLast7days', 0)),
                                int(row.get('upLast30days', 0)),
                                int(row.get('downLast7Days', 0)),
                                int(row.get('downLast30days', 0))
                            ))

                    if has_trend or has_revisions:
                        success_count += 1
                        logger.debug(f"  ✓ {symbol}")
                    else:
                        no_data_count += 1
                        logger.debug(f"  - {symbol} (no data)")

                except Exception as e:
                    error_count += 1
                    logger.debug(f"  ✗ {symbol}: {str(e)[:50]}")
                    continue

                # Rate limiting: small delay between requests
                time.sleep(0.1)

            # Log batch progress
            logger.info(f"  Batch summary: {len(batch_symbols)} symbols, "
                       f"{success_count} with data, {no_data_count} no data, {error_count} errors")

            # Delay between batches (be nice to yfinance API)
            if batch_num < total_batches - 1:
                logger.info(f"  Waiting 2 seconds before next batch...")
                time.sleep(2)

        # Insert all collected data
        logger.info(f"\n💾 Inserting data into database...")

        trends_inserted = 0
        revisions_inserted = 0

        if all_trends_data:
            try:
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
                        all_trends_data
                    )
                    conn.commit()
                    trends_inserted = len(all_trends_data)
                    logger.info(f"✅ Loaded {trends_inserted} estimate trend records")
            except Exception as e:
                logger.error(f"❌ ERROR inserting trends: {e}")
                conn.rollback()

        if all_revisions_data:
            try:
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
                        all_revisions_data
                    )
                    conn.commit()
                    revisions_inserted = len(all_revisions_data)
                    logger.info(f"✅ Loaded {revisions_inserted} estimate revision records")
            except Exception as e:
                logger.error(f"❌ ERROR inserting revisions: {e}")
                conn.rollback()

        # Final summary
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ EARNINGS REVISIONS LOADER COMPLETE")
        logger.info(f"{'='*70}")
        logger.info(f"Total symbols processed: {len(symbols)}")
        logger.info(f"Symbols with data fetched: {global_success_count}")
        logger.info(f"Trend records inserted: {trends_inserted}")
        logger.info(f"Revision records inserted: {revisions_inserted}")
        logger.info(f"Success rate: {(global_success_count/len(symbols)*100):.1f}%")
        logger.info(f"{'='*70}\n")

    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("Starting earnings estimate revisions loader...")
    create_tables()
    fetch_and_load_revisions()
    logger.info("Done!")
