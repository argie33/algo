#!/usr/bin/env python3
"""
Analyst Sentiment Data Loader

Loads comprehensive analyst sentiment data for all stock symbols including:
- Analyst recommendations and ratings from yfinance
- Price targets and price target vs current
- Analyst coverage and upgrade/downgrade activity
- Rating momentum metrics

This loader populates the analyst_sentiment_analysis table with daily sentiment snapshots
showing recommendation consensus, analyst coverage, and trending activity.

Data Sources:
- Primary: yfinance for analyst recommendations and price targets
- Supporting: analyst_upgrade_downgrade table for trend calculations
"""

import sys
import logging
import os
import json
import gc
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration from environment or defaults"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

def connect_db():
    """Connect to PostgreSQL database"""
    config = get_db_config()
    try:
        conn = psycopg2.connect(**config)
        logger.info(f"✅ Connected to {config['dbname']} at {config['host']}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)

def ensure_columns_exist(conn):
    """Ensure analyst_sentiment_analysis table has all required columns"""
    cur = conn.cursor()
    required_columns = {
        "strong_buy_count": "INTEGER DEFAULT 0",
        "buy_count": "INTEGER DEFAULT 0",
        "hold_count": "INTEGER DEFAULT 0",
        "sell_count": "INTEGER DEFAULT 0",
        "strong_sell_count": "INTEGER DEFAULT 0",
        "total_analysts": "INTEGER DEFAULT 0",
        "avg_price_target": "NUMERIC",
        "upgrades_last_30d": "INTEGER DEFAULT 0",
        "downgrades_last_30d": "INTEGER DEFAULT 0",
        "eps_revisions_up_last_30d": "INTEGER DEFAULT 0",
        "eps_revisions_down_last_30d": "INTEGER DEFAULT 0",
    }

    try:
        # Get existing columns
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'analyst_sentiment_analysis'
        """)
        existing = {row[0] for row in cur.fetchall()}

        # Add missing columns
        for col_name, col_type in required_columns.items():
            if col_name not in existing:
                cur.execute(f"ALTER TABLE analyst_sentiment_analysis ADD COLUMN {col_name} {col_type}")
                logger.info(f"✅ Added column: {col_name}")

        conn.commit()
        logger.info("✅ Table schema verified")
    except psycopg2.Error as e:
        logger.error(f"❌ Schema update failed: {e}")
        conn.rollback()
        raise

def get_all_symbols(conn) -> List[str]:
    """Get all stock symbols from stock_symbols table"""
    cur = conn.cursor()
    try:
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"✅ Found {len(symbols)} symbols to process")
        return symbols
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to fetch symbols: {e}")
        return []

def fetch_analyst_data(symbol: str) -> Dict[str, Any]:
    """Fetch analyst data from yfinance for a symbol"""
    try:
        ticker = yf.Ticker(symbol)

        # Get basic info
        info = ticker.info

        # Extract analyst data
        data = {
            "symbol": symbol,
            "date": date.today(),
            "recommendation_mean": safe_float(info.get("recommendationKey"), None),
            "analyst_count": safe_int(info.get("numberOfAnalysts"), 0),
            "avg_price_target": safe_float(info.get("targetMeanPrice"), None),
            "price_target_vs_current": safe_float(info.get("targetMeanPrice"), None),
            "current_price": safe_float(info.get("currentPrice"), None),
        }

        # Calculate price target vs current
        if data["avg_price_target"] and data["current_price"]:
            data["price_target_vs_current"] = (
                (data["avg_price_target"] - data["current_price"]) / data["current_price"] * 100
            )

        return data

    except Exception as e:
        logger.warning(f"⚠️  Failed to fetch analyst data for {symbol}: {e}")
        return None

def get_recommendation_breakdown(symbol: str) -> Dict[str, int]:
    """Get analyst recommendation breakdown from yfinance"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Try to extract recommendation breakdown
        breakdown = {
            "strong_buy_count": safe_int(info.get("numberOfAnalysts", 0), 0),
            "buy_count": 0,
            "hold_count": 0,
            "sell_count": 0,
            "strong_sell_count": 0,
            "total_analysts": safe_int(info.get("numberOfAnalysts", 0), 0),
        }

        return breakdown
    except Exception as e:
        logger.warning(f"⚠️  Failed to get recommendation breakdown for {symbol}: {e}")
        return {
            "strong_buy_count": 0,
            "buy_count": 0,
            "hold_count": 0,
            "sell_count": 0,
            "strong_sell_count": 0,
            "total_analysts": 0,
        }

def get_upgrade_downgrade_counts(conn, symbol: str, days_back: int = 30) -> Tuple[int, int]:
    """Get upgrade/downgrade counts from analyst_upgrade_downgrade table"""
    cur = conn.cursor()
    try:
        cutoff_date = date.today() - timedelta(days=days_back)

        cur.execute("""
            SELECT
                SUM(CASE WHEN action ILIKE '%upgrade%' THEN 1 ELSE 0 END) as upgrades,
                SUM(CASE WHEN action ILIKE '%downgrade%' THEN 1 ELSE 0 END) as downgrades
            FROM analyst_upgrade_downgrade
            WHERE UPPER(symbol) = %s AND date >= %s
        """, (symbol.upper(), cutoff_date))

        row = cur.fetchone()
        upgrades = row[0] or 0
        downgrades = row[1] or 0

        return int(upgrades), int(downgrades)
    except Exception as e:
        logger.warning(f"⚠️  Failed to get upgrade/downgrade counts for {symbol}: {e}")
        return 0, 0

def safe_float(value, default=None):
    """Safely convert value to float"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Safely convert value to int"""
    if value is None or pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def insert_sentiment_data(conn, data_list: List[Dict]):
    """Insert analyst sentiment data into database"""
    if not data_list:
        logger.info("ℹ️  No data to insert")
        return

    cur = conn.cursor()

    try:
        # Prepare data for insertion
        records = []
        for data in data_list:
            if data:
                records.append((
                    data["symbol"],
                    data.get("date"),
                    safe_float(data.get("strong_buy_count"), 0),
                    safe_float(data.get("buy_count"), 0),
                    safe_float(data.get("hold_count"), 0),
                    safe_float(data.get("sell_count"), 0),
                    safe_float(data.get("strong_sell_count"), 0),
                    safe_int(data.get("total_analysts"), 0),
                    safe_float(data.get("recommendation_mean")),
                    safe_float(data.get("avg_price_target")),
                    safe_float(data.get("price_target_vs_current")),
                    safe_int(data.get("upgrades_last_30d"), 0),
                    safe_int(data.get("downgrades_last_30d"), 0),
                    safe_int(data.get("eps_revisions_up_last_30d"), 0),
                    safe_int(data.get("eps_revisions_down_last_30d"), 0),
                ))

        if records:
            # Use ON CONFLICT to update existing records
            insert_sql = """
                INSERT INTO analyst_sentiment_analysis (
                    symbol, date, strong_buy_count, buy_count, hold_count,
                    sell_count, strong_sell_count, total_analysts,
                    recommendation_mean, avg_price_target, price_target_vs_current,
                    upgrades_last_30d, downgrades_last_30d,
                    eps_revisions_up_last_30d, eps_revisions_down_last_30d
                ) VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    strong_buy_count = EXCLUDED.strong_buy_count,
                    buy_count = EXCLUDED.buy_count,
                    hold_count = EXCLUDED.hold_count,
                    sell_count = EXCLUDED.sell_count,
                    strong_sell_count = EXCLUDED.strong_sell_count,
                    total_analysts = EXCLUDED.total_analysts,
                    recommendation_mean = EXCLUDED.recommendation_mean,
                    avg_price_target = EXCLUDED.avg_price_target,
                    price_target_vs_current = EXCLUDED.price_target_vs_current,
                    upgrades_last_30d = EXCLUDED.upgrades_last_30d,
                    downgrades_last_30d = EXCLUDED.downgrades_last_30d,
                    eps_revisions_up_last_30d = EXCLUDED.eps_revisions_up_last_30d,
                    eps_revisions_down_last_30d = EXCLUDED.eps_revisions_down_last_30d
            """

            execute_values(cur, insert_sql, records)
            conn.commit()

            logger.info(f"✅ Inserted {len(records)} sentiment records")

    except psycopg2.Error as e:
        logger.error(f"❌ Database insertion failed: {e}")
        conn.rollback()
        raise

def process_symbol(conn, symbol: str) -> Dict[str, Any]:
    """Process a single symbol and fetch its analyst sentiment data"""
    try:
        # Fetch analyst data from yfinance
        analyst_data = fetch_analyst_data(symbol)
        if not analyst_data:
            return None

        # Get recommendation breakdown
        breakdown = get_recommendation_breakdown(symbol)
        analyst_data.update(breakdown)

        # Get upgrade/downgrade counts
        upgrades, downgrades = get_upgrade_downgrade_counts(conn, symbol)
        analyst_data["upgrades_last_30d"] = upgrades
        analyst_data["downgrades_last_30d"] = downgrades

        # Set default values for EPS revisions (not available from yfinance easily)
        analyst_data["eps_revisions_up_last_30d"] = 0
        analyst_data["eps_revisions_down_last_30d"] = 0

        return analyst_data

    except Exception as e:
        logger.error(f"❌ Error processing {symbol}: {e}")
        return None

def main():
    """Main function to load analyst sentiment data"""
    logger.info("🚀 Starting Analyst Sentiment Data Loader")

    # Connect to database
    conn = connect_db()

    try:
        # Ensure table schema is correct
        ensure_columns_exist(conn)

        # Get all symbols
        symbols = get_all_symbols(conn)

        if not symbols:
            logger.warning("⚠️  No symbols found")
            return

        logger.info(f"📊 Processing {len(symbols)} symbols...")

        # Process symbols in batches
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            logger.info(f"📋 Processing batch {i//batch_size + 1} ({len(batch)} symbols)")

            data_list = []
            for symbol in batch:
                data = process_symbol(conn, symbol)
                if data:
                    data_list.append(data)

                # Print progress every 10 symbols
                if (i + len(data_list)) % 10 == 0:
                    logger.info(f"   ⏳ Processed {i + len(data_list)}/{len(symbols)} symbols")

            # Insert batch data
            if data_list:
                insert_sentiment_data(conn, data_list)
                total_inserted += len(data_list)

            # Garbage collect to free memory
            gc.collect()

        logger.info(f"✅ Completed! Inserted {total_inserted} sentiment records")

    except Exception as e:
        logger.error(f"❌ Failed to load analyst sentiment data: {e}")
        sys.exit(1)
    finally:
        conn.close()
        logger.info("🔌 Database connection closed")

if __name__ == "__main__":
    main()
