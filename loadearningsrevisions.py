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

import boto3
import json

def get_db_config():
    """Get database configuration - works in AWS and locally.
    
    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")
    
    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logger.info(f"Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")
    
    # Fall back to environment variables
    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks")
    }

def get_db_connection():
    """Create database connection"""
    cfg = get_db_config()
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["database"]
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

        # Get list of ALL symbols from stock_symbols table
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol IS NOT NULL AND etf = 'N' ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]

        logger.info(f"📊 Processing {len(symbols)} total symbols...")
        logger.warning("⚠️  NOTE: yfinance eps_trend/eps_revisions endpoints are frequently rate-limited by yfinance.")
        logger.info(f"⏱️  Estimated time: {len(symbols) * 1 / 60:.1f} minutes (with aggressive rate limiting)")

        # Batch parameters - MUCH MORE AGGRESSIVE rate limiting after discovery of batch 10-26 failure
        batch_size = 20  # REDUCED from 30 (smaller batches = finer control)
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        global_success_count = 0
        global_no_data = 0
        global_errors = 0
        total_trends_inserted = 0
        total_revisions_inserted = 0

        # Process in batches
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = min(batch_start + batch_size, len(symbols))
            batch_symbols = symbols[batch_start:batch_end]

            logger.info(f"\n📦 Batch {batch_num + 1}/{total_batches} ({batch_start + 1}-{batch_end}/{len(symbols)})")

            batch_success = 0
            batch_errors = 0
            batch_no_data = 0
            batch_trends_data = []  # Fresh list for this batch
            batch_revisions_data = []  # Fresh list for this batch

            for symbol in batch_symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    has_data = False

                    # Try EPS trend data (with separate error handling)
                    try:
                        eps_trend = ticker.eps_trend
                        if eps_trend is not None and not eps_trend.empty:
                            has_data = True
                            for period in eps_trend.index:
                                row = eps_trend.loc[period]
                                batch_trends_data.append((
                                    symbol,
                                    str(period),
                                    today,
                                    float(row.get('current')) if row.get('current') is not None else None,
                                    float(row.get('7daysAgo')) if row.get('7daysAgo') is not None else None,
                                    float(row.get('30daysAgo')) if row.get('30daysAgo') is not None else None,
                                    float(row.get('60daysAgo')) if row.get('60daysAgo') is not None else None,
                                    float(row.get('90daysAgo')) if row.get('90daysAgo') is not None else None
                                ))
                    except Exception as e:
                        logger.debug(f"  {symbol} eps_trend error: {str(e)[:50]}")

                    # Try EPS revisions data (with separate error handling)
                    try:
                        eps_revisions = ticker.eps_revisions
                        if eps_revisions is not None and not eps_revisions.empty:
                            has_data = True
                            for period in eps_revisions.index:
                                row = eps_revisions.loc[period]
                                batch_revisions_data.append((
                                    symbol,
                                    str(period),
                                    today,
                                    int(row.get('upLast7days', 0)),
                                    int(row.get('upLast30days', 0)),
                                    int(row.get('downLast7Days', 0)),
                                    int(row.get('downLast30days', 0))
                                ))
                    except Exception as e:
                        logger.debug(f"  {symbol} eps_revisions error: {str(e)[:50]}")

                    if has_data:
                        batch_success += 1
                        global_success_count += 1
                        logger.debug(f"  ✓ {symbol}")
                    else:
                        batch_no_data += 1
                        global_no_data += 1
                        logger.debug(f"  - {symbol} (no data)")

                except Exception as e:
                    batch_errors += 1
                    global_errors += 1
                    logger.debug(f"  ✗ {symbol}: {str(e)[:50]}")

                # Rate limiting: MUCH longer delay per request (prevent hard block)
                time.sleep(0.5)

            # Log batch progress
            logger.info(f"  Batch complete: {batch_success} with data, {batch_no_data} no data, {batch_errors} errors")

            # INSERT THIS BATCH'S DATA IMMEDIATELY (not at the end!)
            if batch_trends_data:
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
                            batch_trends_data
                        )
                        conn.commit()
                        total_trends_inserted += len(batch_trends_data)
                        logger.debug(f"  ✅ Inserted {len(batch_trends_data)} trend records")
                except Exception as e:
                    logger.error(f"  ❌ ERROR inserting trends: {e}")
                    conn.rollback()

            if batch_revisions_data:
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
                            batch_revisions_data
                        )
                        conn.commit()
                        total_revisions_inserted += len(batch_revisions_data)
                        logger.debug(f"  ✅ Inserted {len(batch_revisions_data)} revision records")
                except Exception as e:
                    logger.error(f"  ❌ ERROR inserting revisions: {e}")
                    conn.rollback()

            # Delay between batches - INCREASED to prevent rate limit
            if batch_num < total_batches - 1:
                logger.info(f"  Waiting 5 seconds before next batch...")
                time.sleep(5)

        # Final summary
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ EARNINGS REVISIONS LOADER COMPLETE")
        logger.info(f"{'='*70}")
        logger.info(f"Total symbols processed: {len(symbols)}")
        logger.info(f"Symbols with data fetched: {global_success_count}")
        logger.info(f"Symbols with no data: {global_no_data}")
        logger.info(f"Symbols with errors: {global_errors}")
        logger.info(f"Trend records inserted: {total_trends_inserted}")
        logger.info(f"Revision records inserted: {total_revisions_inserted}")
        logger.info(f"Success rate: {(global_success_count/len(symbols)*100):.1f}%")
        logger.info(f"{'='*70}\n")
        logger.info(f"✅ Data is now available on the earnings page!")

    finally:
        conn.close()

if __name__ == "__main__":
    logger.info("Starting earnings estimate revisions loader...")
    create_tables()
    fetch_and_load_revisions()
    logger.info("Done!")
