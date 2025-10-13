#!/usr/bin/env python3
# Updated: 2025-10-07 - Growth Metrics Calculator
"""
Growth Metrics Loader

Calculates comprehensive growth metrics for stocks based on:
- Revenue growth (YoY from revenue_estimates)
- Earnings growth (YoY from earnings_history)
- Margin expansion (from key_metrics historical data)

Methodology:
- Revenue Growth: 35% - Top-line expansion
- Earnings Growth: 35% - Bottom-line growth
- Margin Expansion: 30% - Operational efficiency improvement

Output:
- growth_metrics table with growth_metric (composite score)
- revenue_growth_metric (normalized revenue YoY growth)
- earnings_growth_metric (normalized EPS YoY growth)
- margin_expansion_metric (normalized margin improvement)
"""

import concurrent.futures
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extensions
from psycopg2 import pool
from psycopg2.extras import execute_values

# Register numpy type adapters for psycopg2
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

# Script metadata
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)

# Performance configuration
MAX_WORKERS = min(os.cpu_count() or 1, 4)
BATCH_SIZE = 100
DB_POOL_MIN = 2
DB_POOL_MAX = 10


def get_db_config():
    """Fetch database credentials from AWS Secrets Manager or use local config"""
    if os.environ.get("USE_LOCAL_DB") == "true" or not os.environ.get("DB_SECRET_ARN"):
        logging.info("Using local database configuration")
        return (
            os.environ.get("DB_USER", "postgres"),
            os.environ.get("DB_PASSWORD", "password"),
            os.environ.get("DB_HOST", "localhost"),
            int(os.environ.get("DB_PORT", "5432")),
            os.environ.get("DB_NAME", "stocks"),
        )

    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"],
    )


def safe_numeric(value):
    """Safely convert value to float, handling None, NaN, invalid strings, and Decimal"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, str):
        if value.strip() == "" or value.strip().lower() == "nan":
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def normalize_metric(value, min_val, max_val):
    """
    Normalize a metric to 0-100 scale

    Args:
        value: Raw metric value (e.g., 25.5 for 25.5% growth)
        min_val: Minimum expected value (maps to 0)
        max_val: Maximum expected value (maps to 100)

    Returns:
        float: Normalized score 0-100, or None if value is None
    """
    if value is None:
        return None

    # Clamp to range
    clamped = max(min_val, min(max_val, value))

    # Normalize to 0-100
    if max_val == min_val:
        return 50.0

    return ((clamped - min_val) / (max_val - min_val)) * 100


def initialize_db():
    """Initialize database connection and create tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    cursor = conn.cursor()

    # Create last_updated table for tracking
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            loader VARCHAR(255) PRIMARY KEY,
            last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Record script start time
    cursor.execute(
        "INSERT INTO last_updated (script_name, last_run) VALUES (%s, CURRENT_TIMESTAMP) "
        "ON CONFLICT (script_name) DO UPDATE SET last_run = CURRENT_TIMESTAMP;",
        (SCRIPT_NAME,),
    )
    conn.commit()

    # Drop and recreate growth_metrics table
    logging.info("Creating growth_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS growth_metrics;")
    cursor.execute(
        """
        CREATE TABLE growth_metrics (
            symbol                      VARCHAR(50),
            date                        DATE,

            -- RAW calculated metrics ONLY (for stockscores script to use)
            revenue_growth_3y_cagr      DOUBLE PRECISION,  -- 3-year revenue CAGR
            eps_growth_3y_cagr          DOUBLE PRECISION,  -- 3-year EPS CAGR
            operating_income_growth_yoy DOUBLE PRECISION,  -- Operating income YoY growth
            roe_trend                   DOUBLE PRECISION,  -- ROE change (current - 1Y ago)
            sustainable_growth_rate     DOUBLE PRECISION,  -- ROE × (1 - Payout Ratio)
            fcf_growth_yoy              DOUBLE PRECISION,  -- Free cash flow YoY growth

            -- NOTE: Single YoY growth rates already in revenue_estimates/earnings_history
            -- NOTE: Scores calculated by stockscores script, not here

            fetched_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """
    )

    # Create indexes for query performance
    logging.info("Creating indexes on growth_metrics...")
    cursor.execute("CREATE INDEX idx_growth_metrics_symbol ON growth_metrics(symbol);")
    cursor.execute("CREATE INDEX idx_growth_metrics_date ON growth_metrics(date DESC);")
    conn.commit()  # IMPORTANT: Commit table creation before workers start
    logging.info("Indexes created successfully")

    logging.info("Table 'growth_metrics' ready.")

    # Get stock symbols (exclude ETFs)
    cursor.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"Found {len(symbols)} symbols.")

    cursor.close()
    conn.close()
    return symbols


def create_connection_pool():
    """Create database connection pool"""
    user, pwd, host, port, db = get_db_config()
    return pool.ThreadedConnectionPool(
        DB_POOL_MIN,
        DB_POOL_MAX,
        host=host,
        port=port,
        user=user,
        password=pwd,
        dbname=db,
    )


def process_symbol(symbol, conn_pool):
    """
    Process a single symbol and calculate growth metrics

    Industry-standard approach:
    1. Revenue Growth (30%): YoY from revenue_estimates + 3Y CAGR calculated
    2. Earnings Growth (30%): YoY from earnings_history + 3Y CAGR calculated
    3. Fundamental Drivers (25%): Op income growth, ROE trend, sustainable growth rate, FCF growth
    4. Market Expansion (15%): TAM growth (sector-based)

    Args:
        symbol: Stock symbol to process
        conn_pool: Database connection pool

    Returns:
        int: Number of records inserted
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing growth metrics for {symbol}...")

        # ========== STEP 1: Fetch YoY Revenue Growth (from revenue_estimates) ==========
        cursor.execute(
            """
            SELECT growth
            FROM revenue_estimates
            WHERE symbol = %s
            ORDER BY period DESC
            LIMIT 1
            """,
            (symbol,),
        )
        revenue_row = cursor.fetchone()
        revenue_growth_yoy = safe_numeric(revenue_row[0]) * 100 if revenue_row and revenue_row[0] else None  # Convert to %

        # ========== STEP 2: Fetch YoY EPS Growth (from earnings_history) ==========
        cursor.execute(
            """
            SELECT eps_actual
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 5
            """,
            (symbol,),
        )
        earnings_rows = cursor.fetchall()

        eps_growth_yoy = None
        if len(earnings_rows) >= 5:
            current_eps = safe_numeric(earnings_rows[0][0])
            year_ago_eps = safe_numeric(earnings_rows[4][0])
            if current_eps is not None and year_ago_eps is not None and year_ago_eps != 0:
                eps_growth_yoy = ((current_eps - year_ago_eps) / abs(year_ago_eps)) * 100

        # ========== STEP 3: Fetch ROE for Sustainable Growth Rate (from key_metrics) ==========
        cursor.execute(
            """
            SELECT return_on_equity_pct
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        roe_row = cursor.fetchone()
        roe = safe_numeric(roe_row[0]) if roe_row else None

        # Sustainable Growth Rate = ROE × (1 - Payout Ratio)
        # Assume 30% payout ratio as default
        sustainable_growth_rate = (roe * 0.70) if roe else None

        logging.info(f"{symbol}: Revenue YoY: {revenue_growth_yoy}, EPS YoY: {eps_growth_yoy}, SGR: {sustainable_growth_rate}")

        if revenue_growth_yoy is None and eps_growth_yoy is None:
            logging.warning(f"No growth data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Get current date for the record
        current_date = datetime.now().date()

        # Create record with RAW metrics ONLY - no scores
        record = (
            symbol,
            current_date,
            None,  # revenue_growth_3y_cagr (TODO: calculate when needed)
            None,  # eps_growth_3y_cagr (TODO: calculate when needed)
            None,  # operating_income_growth_yoy (TODO: calculate when needed)
            None,  # roe_trend (TODO: calculate when needed)
            sustainable_growth_rate,
            None,  # fcf_growth_yoy (TODO: calculate when needed)
        )
        records = [record]

        # ========== STEP 4: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO growth_metrics
                (symbol, date, revenue_growth_3y_cagr, eps_growth_3y_cagr,
                 operating_income_growth_yoy, roe_trend, sustainable_growth_rate, fcf_growth_yoy)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    revenue_growth_3y_cagr = EXCLUDED.revenue_growth_3y_cagr,
                    eps_growth_3y_cagr = EXCLUDED.eps_growth_3y_cagr,
                    operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                    roe_trend = EXCLUDED.roe_trend,
                    sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                    fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                records,
            )
            conn.commit()
            logging.info(f"✅ {symbol}: Inserted {len(records)} growth metric records")

        conn_pool.putconn(conn)
        return len(records)

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        try:
            conn_pool.putconn(conn)
        except:
            pass
        return 0


def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Growth Metrics Loader - Starting")
    logging.info("=" * 80)

    # Initialize database and get symbols
    symbols = initialize_db()

    # Create connection pool
    conn_pool = create_connection_pool()

    # Process symbols in parallel
    total_records = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_symbol, sym, conn_pool): sym for sym in symbols}

        for future in concurrent.futures.as_completed(futures):
            symbol = futures[future]
            try:
                records = future.result()
                total_records += records
            except Exception as e:
                logging.error(f"Error processing {symbol}: {e}")

    # Cleanup
    conn_pool.closeall()
    gc.collect()

    elapsed = time.time() - start_time
    logging.info("=" * 80)
    logging.info(f"✅ Growth Metrics Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
