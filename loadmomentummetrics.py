#!/usr/bin/env python3
# Updated: 2025-10-14 - Dual Momentum (Relative + Absolute)
"""
Momentum Metrics Loader - Dual Momentum Factor

Calculates DUAL MOMENTUM metrics combining:
1. RELATIVE MOMENTUM (Cross-Sectional) - vs other stocks
2. ABSOLUTE MOMENTUM (Time-Series) - vs itself

Based on Gary Antonacci's dual momentum research and industry standards.

RELATIVE MOMENTUM:
- momentum_12m_1: 12-month return excluding last month (academic standard)
- momentum_6m: 6-month return
- momentum_3m: 3-month return
- risk_adjusted_momentum: 12M return / 12M volatility (Sharpe-style)

ABSOLUTE MOMENTUM:
- price_vs_sma_50: Current price vs 50-day MA (%)
- price_vs_sma_200: Current price vs 200-day MA (%)
- price_vs_52w_high: Current price vs 52-week high (%)

Output:
- momentum_metrics table with dual momentum components
"""

import concurrent.futures
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime
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


def initialize_db():
    """Initialize database connection and create tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    cursor = conn.cursor()

    # Create last_updated table for tracking
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
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

    # Drop and recreate momentum_metrics table with dual momentum schema
    logging.info("Creating momentum_metrics table with dual momentum schema...")
    cursor.execute("DROP TABLE IF EXISTS momentum_metrics;")
    cursor.execute(
        """
        CREATE TABLE momentum_metrics (
            symbol                      VARCHAR(50),
            date                        DATE,

            -- RELATIVE MOMENTUM (vs other stocks)
            momentum_12m_1              DOUBLE PRECISION,  -- 12-month return excluding last month
            momentum_6m                 DOUBLE PRECISION,  -- 6-month return
            momentum_3m                 DOUBLE PRECISION,  -- 3-month return
            risk_adjusted_momentum      DOUBLE PRECISION,  -- 12M return / 12M volatility

            -- ABSOLUTE MOMENTUM (vs itself)
            price_vs_sma_50             DOUBLE PRECISION,  -- % above/below 50-day MA
            price_vs_sma_200            DOUBLE PRECISION,  -- % above/below 200-day MA
            price_vs_52w_high           DOUBLE PRECISION,  -- % of 52-week high

            -- Supporting data
            current_price               DOUBLE PRECISION,  -- Current closing price
            sma_50                      DOUBLE PRECISION,  -- 50-day moving average
            sma_200                     DOUBLE PRECISION,  -- 200-day moving average
            high_52w                    DOUBLE PRECISION,  -- 52-week high
            volatility_12m              DOUBLE PRECISION,  -- 12-month annualized volatility

            fetched_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """
    )

    # Create indexes for query performance
    logging.info("Creating indexes on momentum_metrics...")
    cursor.execute("CREATE INDEX idx_momentum_metrics_symbol ON momentum_metrics(symbol);")
    cursor.execute("CREATE INDEX idx_momentum_metrics_date ON momentum_metrics(date DESC);")
    conn.commit()
    logging.info("Indexes created successfully")

    logging.info("Table 'momentum_metrics' ready with dual momentum schema.")

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
    Process a single symbol and calculate dual momentum metrics

    RELATIVE MOMENTUM (Cross-Sectional):
    - 12-month return excluding last month
    - 6-month return
    - 3-month return
    - Risk-adjusted momentum

    ABSOLUTE MOMENTUM (Time-Series):
    - Price vs 50-day MA
    - Price vs 200-day MA
    - Price vs 52-week high

    Args:
        symbol: Stock symbol to process
        conn_pool: Database connection pool

    Returns:
        int: Number of records inserted
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing dual momentum for {symbol}...")

        # ========== STEP 1: Fetch Daily Price Data ==========
        # Get last 252 trading days (approx 1 year)
        cursor.execute(
            """
            SELECT date, close
            FROM price_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 252
            """,
            (symbol,),
        )
        price_data = cursor.fetchall()
        logging.info(f"{symbol}: Found {len(price_data)} daily price records")

        # Extract prices and dates (reverse to oldest-first order)
        # Note: If fewer than 63 days, individual metrics will be NULL but stock record will be inserted
        if len(price_data) > 0:
            prices = [safe_numeric(row[1]) for row in reversed(price_data)]
            dates = [row[0] for row in reversed(price_data)]
        else:
            # No price data at all - still insert record with all NULLs
            prices = []
            dates = []
            logging.warning(f"No price data for {symbol}, creating NULL momentum record")

        # ========== STEP 2: Calculate RELATIVE MOMENTUM ==========
        current_date = datetime.now().date()
        current_price = prices[-1] if len(prices) > 0 else None

        # --- 2.1: 12-Month Return Excluding Last Month (12-1) ---
        # Academic standard: t-252 to t-21 (skip last month)
        momentum_12m_1 = None
        if len(prices) >= 252:
            price_252d_ago = prices[-252]
            price_21d_ago = prices[-21]
            if price_252d_ago and price_21d_ago and price_252d_ago > 0:
                momentum_12m_1 = ((price_21d_ago - price_252d_ago) / price_252d_ago) * 100
                logging.info(f"{symbol}: 12M-1 return = {momentum_12m_1:.2f}%")

        # --- 2.2: 6-Month Return ---
        momentum_6m = None
        if len(prices) >= 120:
            price_120d_ago = prices[-120]
            if price_120d_ago and current_price and price_120d_ago > 0:
                momentum_6m = ((current_price - price_120d_ago) / price_120d_ago) * 100
                logging.info(f"{symbol}: 6M return = {momentum_6m:.2f}%")

        # --- 2.3: 3-Month Return ---
        momentum_3m = None
        if len(prices) >= 63:
            price_63d_ago = prices[-63]
            if price_63d_ago and current_price and price_63d_ago > 0:
                momentum_3m = ((current_price - price_63d_ago) / price_63d_ago) * 100
                logging.info(f"{symbol}: 3M return = {momentum_3m:.2f}%")

        # --- 2.4: Risk-Adjusted Momentum (12M return / volatility) ---
        risk_adjusted = None
        volatility_12m = None

        if len(prices) >= 252:
            # Calculate daily returns for last 252 days
            returns = []
            for i in range(len(prices) - 252, len(prices)):
                if i > 0 and prices[i-1] and prices[i] and prices[i-1] > 0:
                    daily_return = (prices[i] - prices[i-1]) / prices[i-1]
                    returns.append(daily_return)

            if len(returns) >= 200:
                # Annualized volatility
                volatility_12m = np.std(returns) * np.sqrt(252)

                # Calculate 12-month return for risk adjustment
                price_252d_ago = prices[-252]
                if price_252d_ago and current_price and price_252d_ago > 0:
                    return_12m = ((current_price - price_252d_ago) / price_252d_ago) * 100

                    if volatility_12m > 0:
                        # Risk-adjusted = return / volatility (Sharpe-style, no risk-free rate)
                        risk_adjusted = return_12m / (volatility_12m * 100)
                        logging.info(f"{symbol}: Risk-adjusted = {risk_adjusted:.2f} (return={return_12m:.2f}%, vol={volatility_12m*100:.2f}%)")

        # ========== STEP 3: Calculate ABSOLUTE MOMENTUM ==========

        # --- 3.1: Calculate Moving Averages ---
        sma_50 = None
        sma_200 = None

        if len(prices) >= 50:
            sma_50 = np.mean(prices[-50:])

        if len(prices) >= 200:
            sma_200 = np.mean(prices[-200:])

        # --- 3.2: Price vs 50-day MA ---
        price_vs_sma_50 = None
        if sma_50 and current_price and sma_50 > 0:
            price_vs_sma_50 = ((current_price - sma_50) / sma_50) * 100
            logging.info(f"{symbol}: Price vs SMA50 = {price_vs_sma_50:+.2f}%")

        # --- 3.3: Price vs 200-day MA ---
        price_vs_sma_200 = None
        if sma_200 and current_price and sma_200 > 0:
            price_vs_sma_200 = ((current_price - sma_200) / sma_200) * 100
            logging.info(f"{symbol}: Price vs SMA200 = {price_vs_sma_200:+.2f}%")

        # --- 3.4: Price vs 52-Week High ---
        high_52w = None
        price_vs_52w_high = None

        if len(prices) >= 252:
            high_52w = max([p for p in prices[-252:] if p is not None and p > 0])

            if high_52w and current_price and high_52w > 0:
                price_vs_52w_high = (current_price / high_52w) * 100
                logging.info(f"{symbol}: Price vs 52w high = {price_vs_52w_high:.2f}% (current={current_price:.2f}, high={high_52w:.2f})")

        # ========== STEP 4: Insert Record ==========
        record = (
            symbol,
            current_date,
            # Relative momentum
            momentum_12m_1,
            momentum_6m,
            momentum_3m,
            risk_adjusted,
            # Absolute momentum
            price_vs_sma_50,
            price_vs_sma_200,
            price_vs_52w_high,
            # Supporting data
            current_price,
            sma_50,
            sma_200,
            high_52w,
            volatility_12m,
        )

        execute_values(
            cursor,
            """
            INSERT INTO momentum_metrics
            (symbol, date,
             momentum_12m_1, momentum_6m, momentum_3m, risk_adjusted_momentum,
             price_vs_sma_50, price_vs_sma_200, price_vs_52w_high,
             current_price, sma_50, sma_200, high_52w, volatility_12m)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                momentum_12m_1 = EXCLUDED.momentum_12m_1,
                momentum_6m = EXCLUDED.momentum_6m,
                momentum_3m = EXCLUDED.momentum_3m,
                risk_adjusted_momentum = EXCLUDED.risk_adjusted_momentum,
                price_vs_sma_50 = EXCLUDED.price_vs_sma_50,
                price_vs_sma_200 = EXCLUDED.price_vs_sma_200,
                price_vs_52w_high = EXCLUDED.price_vs_52w_high,
                current_price = EXCLUDED.current_price,
                sma_50 = EXCLUDED.sma_50,
                sma_200 = EXCLUDED.sma_200,
                high_52w = EXCLUDED.high_52w,
                volatility_12m = EXCLUDED.volatility_12m,
                fetched_at = CURRENT_TIMESTAMP
            """,
            [record],
        )
        conn.commit()
        logging.info(f"✅ {symbol}: Inserted dual momentum metrics")

        conn_pool.putconn(conn)
        return 1

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        try:
            conn_pool.putconn(conn)
        except Exception as e:
            logging.error(f"Exception in {file_path}: {e}")
            pass
        return 0


def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Dual Momentum Metrics Loader - Starting")
    logging.info("Relative: 12M-1, 6M, 3M, Risk-Adjusted")
    logging.info("Absolute: Price vs SMA50, SMA200, 52w High")
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
    logging.info(f"✅ Dual Momentum Metrics Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
