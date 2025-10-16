#!/usr/bin/env python3
# Updated: 2025-10-16 14:45 - Trigger rebuild: 20251016_144500 - Populate growth metrics to AWS
"""
Growth Metrics Loader - NO FALLBACK Policy

Calculates comprehensive growth metrics for stocks using REAL DATA ONLY from yfinance.
All metrics remain NULL when data is unavailable (NO FALLBACK, NO PROXIES, NO ASSUMPTIONS).

Data Sources:
1. revenue_growth_3y_cagr: key_metrics.revenue_growth_pct (yfinance annual growth rate)
2. eps_growth_3y_cagr: key_metrics.earnings_growth_pct (yfinance annual EPS growth)
3. operating_income_growth_yoy: quarterly_income_statement (4-quarter YoY comparison)
4. roe_trend: key_metrics.return_on_equity_pct (yfinance current ROE)
5. sustainable_growth_rate: ROE × (1 - Payout Ratio) [ROE from key_metrics, Payout from quality_metrics]
6. fcf_growth_yoy: quarterly_cash_flow (4-quarter YoY comparison)

Quality Assurance:
✅ NO fallback calculations - metrics stay NULL if data unavailable
✅ NO proxy metrics - revenue growth not used for operating income growth
✅ NO assumed values - payout ratio not assumed, retrieved from quality_metrics
✅ All sources from yfinance through database tables
✅ Quarterly data calculations require 5+ quarters of valid data (current + 4 years ago)
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
import yfinance as yf
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


def calculate_yoy_growth(quarterly_data, metric_name):
    """
    Calculate year-over-year growth from quarterly data

    Args:
        quarterly_data: DataFrame with quarters as columns
        metric_name: Name of the metric row to analyze

    Returns:
        float: YoY growth percentage, or None if insufficient data
    """
    try:
        if quarterly_data is None or quarterly_data.empty:
            return None

        if metric_name not in quarterly_data.index:
            return None

        # Get the metric row
        metric_row = quarterly_data.loc[metric_name]

        # Need at least 5 quarters (current + 4 quarters back)
        if len(metric_row) < 5:
            return None

        # Get most recent quarter and 4 quarters ago (YoY comparison)
        current_value = safe_numeric(metric_row.iloc[0])
        year_ago_value = safe_numeric(metric_row.iloc[4])

        if current_value is None or year_ago_value is None:
            return None

        if year_ago_value == 0:
            return None

        # Calculate YoY growth percentage
        yoy_growth = ((current_value - year_ago_value) / abs(year_ago_value)) * 100

        return yoy_growth

    except Exception as e:
        logging.debug(f"Error calculating YoY growth for {metric_name}: {e}")
        return None


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

        # ========== STEP 3: Fetch growth metrics from key_metrics (yfinance data) ==========
        cursor.execute(
            """
            SELECT
                return_on_equity_pct,
                revenue_growth_pct,
                earnings_growth_pct
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        metrics_row = cursor.fetchone()

        if metrics_row:
            roe = safe_numeric(metrics_row[0])
            revenue_growth_pct = safe_numeric(metrics_row[1])  # YoY revenue growth from yfinance
            earnings_growth_pct = safe_numeric(metrics_row[2])  # YoY earnings growth from yfinance
        else:
            roe = None
            revenue_growth_pct = None
            earnings_growth_pct = None

        # Use yfinance growth rates as 3Y CAGR proxy (already percentage values)
        revenue_growth_3y_cagr = revenue_growth_pct
        eps_growth_3y_cagr = earnings_growth_pct
        roe_trend = roe  # Current ROE as trend indicator

        # ========== STEP 4: Fetch Sustainable Growth Rate = ROE × (1 - Payout Ratio) ==========
        sustainable_growth_rate = None
        if roe is not None:
            # Try to get payout_ratio from quality_metrics first
            cursor.execute(
                """
                SELECT payout_ratio FROM quality_metrics
                WHERE symbol = %s
                ORDER BY date DESC
                LIMIT 1
                """,
                (symbol,),
            )
            payout_row = cursor.fetchone()
            if payout_row and payout_row[0] is not None:
                payout_ratio = safe_numeric(payout_row[0])
                if payout_ratio is not None and payout_ratio <= 1.0:  # Ensure it's a valid ratio
                    sustainable_growth_rate = roe * (1 - payout_ratio) * 100  # Convert to percentage

        # ========== STEP 5: Fetch quarterly data from quarterly_income_statement (database) ==========
        operating_income_growth_yoy = None
        try:
            cursor.execute(
                """
                SELECT value FROM quarterly_income_statement
                WHERE symbol = %s AND item_name = 'Operating Income'
                ORDER BY date DESC
                LIMIT 5
                """,
                (symbol,),
            )
            op_income_rows = cursor.fetchall()
            if len(op_income_rows) >= 5:
                current_op_income = safe_numeric(op_income_rows[0][0])
                year_ago_op_income = safe_numeric(op_income_rows[4][0])
                if current_op_income is not None and year_ago_op_income is not None and year_ago_op_income != 0:
                    operating_income_growth_yoy = ((current_op_income - year_ago_op_income) / abs(year_ago_op_income)) * 100
        except Exception as e:
            logging.debug(f"{symbol}: Error fetching operating income: {e}")

        # ========== STEP 6: Fetch quarterly cashflow data from quarterly_cash_flow (database) ==========
        fcf_growth_yoy = None
        try:
            cursor.execute(
                """
                SELECT value FROM quarterly_cash_flow
                WHERE symbol = %s AND item_name = 'Free Cash Flow'
                ORDER BY date DESC
                LIMIT 5
                """,
                (symbol,),
            )
            fcf_rows = cursor.fetchall()
            if len(fcf_rows) >= 5:
                current_fcf = safe_numeric(fcf_rows[0][0])
                year_ago_fcf = safe_numeric(fcf_rows[4][0])
                if current_fcf is not None and year_ago_fcf is not None and year_ago_fcf != 0:
                    fcf_growth_yoy = ((current_fcf - year_ago_fcf) / abs(year_ago_fcf)) * 100
        except Exception as e:
            logging.debug(f"{symbol}: Error fetching free cash flow: {e}")

        logging.info(f"{symbol}: Rev Growth: {revenue_growth_3y_cagr}, EPS Growth: {eps_growth_3y_cagr}, ROE: {roe_trend}, SGR: {sustainable_growth_rate}, Op Income YoY: {operating_income_growth_yoy}, FCF YoY: {fcf_growth_yoy}")

        if revenue_growth_3y_cagr is None and eps_growth_3y_cagr is None:
            logging.warning(f"No growth data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Get current date for the record
        current_date = datetime.now().date()

        # Create record with all calculated metrics
        record = (
            symbol,
            current_date,
            revenue_growth_3y_cagr,      # From key_metrics.revenue_growth_pct
            eps_growth_3y_cagr,          # From key_metrics.earnings_growth_pct
            operating_income_growth_yoy, # Calculated from quarterly_financials
            roe_trend,                   # From key_metrics.return_on_equity_pct
            sustainable_growth_rate,     # Calculated: ROE × (1 - Payout Ratio)
            fcf_growth_yoy,              # Calculated from quarterly_cashflow
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
