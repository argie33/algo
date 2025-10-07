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
            growth_metric               DOUBLE PRECISION,  -- Composite growth score (0-100)
            revenue_growth_metric       DOUBLE PRECISION,  -- Revenue YoY growth % normalized
            earnings_growth_metric      DOUBLE PRECISION,  -- EPS YoY growth % normalized
            margin_expansion_metric     DOUBLE PRECISION,  -- Margin improvement normalized
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

    Calculates:
    1. Revenue growth from revenue_estimates (YoY)
    2. Earnings growth from earnings_history (YoY EPS growth)
    3. Margin expansion from key_metrics (comparing current to historical)

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

        # ========== STEP 1: Fetch Revenue Growth Data ==========
        cursor.execute(
            """
            SELECT period, growth, avg_estimate, year_ago_revenue
            FROM revenue_estimates
            WHERE symbol = %s
            ORDER BY period DESC
            LIMIT 8
            """,
            (symbol,),
        )
        revenue_data = cursor.fetchall()
        logging.info(f"{symbol}: Found {len(revenue_data)} revenue records")

        # ========== STEP 2: Fetch Earnings Growth Data ==========
        cursor.execute(
            """
            SELECT quarter, eps_actual
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 8
            """,
            (symbol,),
        )
        earnings_data = cursor.fetchall()
        logging.info(f"{symbol}: Found {len(earnings_data)} earnings records")

        # ========== STEP 3: Fetch Margin Data (current) ==========
        cursor.execute(
            """
            SELECT
                profit_margin_pct,
                gross_margin_pct,
                ebitda_margin_pct,
                operating_margin_pct
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        margin_row = cursor.fetchone()
        logging.info(f"{symbol}: Margin row: {margin_row}")

        if not revenue_data and not earnings_data:
            logging.warning(f"No growth data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # ========== STEP 4: Calculate Growth Metrics ==========
        records = []
        current_date = datetime.now().date()

        # Revenue growth metric (use most recent quarter)
        # NOTE: revenue_estimates.growth is in decimal format (0.05 = 5%), convert to percentage
        revenue_growth_pct = None
        if revenue_data and len(revenue_data) > 0:
            growth_decimal = safe_numeric(revenue_data[0][1])  # growth column
            if growth_decimal is not None:
                revenue_growth_pct = growth_decimal * 100  # Convert to percentage
                logging.info(f"{symbol}: Revenue growth = {revenue_growth_pct}% (from {growth_decimal})")

        # Earnings growth metric (YoY - compare Q0 to Q4)
        earnings_growth_pct = None
        if earnings_data and len(earnings_data) >= 5:
            current_eps = safe_numeric(earnings_data[0][1])
            year_ago_eps = safe_numeric(earnings_data[4][1])

            if current_eps is not None and year_ago_eps is not None and year_ago_eps != 0:
                earnings_growth_pct = ((current_eps - year_ago_eps) / abs(year_ago_eps)) * 100

        # Margin expansion metric (simplified - using current profit margin as proxy)
        # In a more sophisticated version, this would compare current to historical margins
        # NOTE: key_metrics.profit_margin_pct is in decimal format (0.15 = 15%), convert to percentage
        margin_expansion_pct = None
        if margin_row:
            profit_margin_decimal = safe_numeric(margin_row[0])
            if profit_margin_decimal is not None:
                # Convert decimal to percentage and use as expansion metric
                margin_expansion_pct = profit_margin_decimal * 100
                logging.info(f"{symbol}: Margin = {margin_expansion_pct}% (from {profit_margin_decimal})")

        # ========== STEP 5: Normalize Metrics (0-100 scale) ==========
        # Revenue growth: -20% to +60% maps to 0-100
        revenue_growth_normalized = normalize_metric(revenue_growth_pct, -20, 60)
        logging.info(f"{symbol}: Revenue normalized = {revenue_growth_normalized}")

        # Earnings growth: -30% to +60% maps to 0-100
        earnings_growth_normalized = normalize_metric(earnings_growth_pct, -30, 60)
        logging.info(f"{symbol}: Earnings normalized = {earnings_growth_normalized}")

        # Margin expansion: -10% to +30% maps to 0-100
        margin_expansion_normalized = normalize_metric(margin_expansion_pct, -10, 30)
        logging.info(f"{symbol}: Margin normalized = {margin_expansion_normalized}")

        # ========== STEP 6: Calculate Composite Growth Score ==========
        # Weighted average: Revenue 35%, Earnings 35%, Margin 30%
        components = []
        weights = []

        if revenue_growth_normalized is not None:
            components.append(revenue_growth_normalized * 0.35)
            weights.append(0.35)

        if earnings_growth_normalized is not None:
            components.append(earnings_growth_normalized * 0.35)
            weights.append(0.35)

        if margin_expansion_normalized is not None:
            components.append(margin_expansion_normalized * 0.30)
            weights.append(0.30)

        # Calculate weighted composite score
        if components:
            total_weight = sum(weights)
            composite_score = sum(components) / total_weight if total_weight > 0 else None
        else:
            composite_score = None

        # Create record
        record = (
            symbol,
            current_date,
            composite_score,
            revenue_growth_normalized,
            earnings_growth_normalized,
            margin_expansion_normalized,
        )
        records.append(record)

        # ========== STEP 7: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO growth_metrics
                (symbol, date, growth_metric, revenue_growth_metric,
                 earnings_growth_metric, margin_expansion_metric)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    growth_metric = EXCLUDED.growth_metric,
                    revenue_growth_metric = EXCLUDED.revenue_growth_metric,
                    earnings_growth_metric = EXCLUDED.earnings_growth_metric,
                    margin_expansion_metric = EXCLUDED.margin_expansion_metric,
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
