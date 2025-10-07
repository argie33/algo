#!/usr/bin/env python3
# Updated: 2025-10-07 - Momentum Metrics Calculator
"""
Momentum Metrics Loader

Calculates comprehensive momentum metrics for stocks based on:
- Price momentum across multiple timeframes (3m, 6m, 12m)
- JT Momentum (12-1 month momentum excluding most recent month)
- Risk-adjusted momentum (momentum per unit of volatility)

Methodology:
- Momentum Strength: 35% - Composite momentum score
- JT Momentum 12-1: 25% - Classic momentum indicator
- 3M/6M Momentum: 20% each - Short-term trends
- Risk-Adjusted: 20% - Volatility-adjusted momentum

Output:
- momentum_metrics table with momentum_strength (composite score)
- jt_momentum_12_1 (12-month momentum excluding last month)
- momentum_3m (3-month price momentum)
- momentum_6m (6-month price momentum)
- risk_adjusted_momentum (Sharpe-style momentum metric)
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
        value: Raw metric value
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


def calculate_momentum(prices):
    """
    Calculate momentum as percentage return.

    Args:
        prices: List of prices [oldest, ..., newest]

    Returns:
        float: Momentum as percentage (e.g., 15.5 for 15.5% gain)
    """
    if not prices or len(prices) < 2:
        return None

    valid_prices = [p for p in prices if p is not None and p > 0]
    if len(valid_prices) < 2:
        return None

    oldest = valid_prices[0]
    newest = valid_prices[-1]

    if oldest <= 0:
        return None

    momentum_pct = ((newest - oldest) / oldest) * 100
    return momentum_pct


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

    # Drop and recreate momentum_metrics table
    logging.info("Creating momentum_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS momentum_metrics;")
    cursor.execute(
        """
        CREATE TABLE momentum_metrics (
            symbol                      VARCHAR(50),
            date                        DATE,
            momentum_strength           DOUBLE PRECISION,  -- Composite momentum score (0-100)
            jt_momentum_12_1            DOUBLE PRECISION,  -- 12-1 month momentum normalized
            momentum_3m                 DOUBLE PRECISION,  -- 3-month momentum normalized
            momentum_6m                 DOUBLE PRECISION,  -- 6-month momentum normalized
            risk_adjusted_momentum      DOUBLE PRECISION,  -- Volatility-adjusted momentum
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

    logging.info("Table 'momentum_metrics' ready.")

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
    Process a single symbol and calculate momentum metrics

    Calculates:
    1. 3-month momentum (last 63 trading days)
    2. 6-month momentum (last 126 trading days)
    3. JT Momentum 12-1 (252 to 21 trading days ago)
    4. Risk-adjusted momentum (momentum / volatility)

    Args:
        symbol: Stock symbol to process
        conn_pool: Database connection pool

    Returns:
        int: Number of records inserted
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing momentum metrics for {symbol}...")

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

        if len(price_data) < 63:
            logging.warning(f"Insufficient price data for {symbol}, need at least 63 days, got {len(price_data)}")
            conn_pool.putconn(conn)
            return 0

        # Extract prices (reverse to oldest-first order)
        prices = [safe_numeric(row[1]) for row in reversed(price_data)]

        # ========== STEP 2: Calculate Momentum Metrics ==========
        records = []
        current_date = datetime.now().date()

        # --- 2.1: 3-Month Momentum (last 63 days) ---
        # Compare current price to price 63 days ago
        momentum_3m_pct = None
        if len(prices) >= 63:
            price_63d_ago = prices[-63]
            current_price = prices[-1]
            if price_63d_ago and current_price and price_63d_ago > 0:
                momentum_3m_pct = ((current_price - price_63d_ago) / price_63d_ago) * 100
                logging.info(f"{symbol}: 3M momentum = {momentum_3m_pct:.2f}%")

        # Normalize: -30% to +60% maps to 0-100
        momentum_3m_normalized = normalize_metric(momentum_3m_pct, -30, 60)

        # --- 2.2: 6-Month Momentum (last 126 days) ---
        momentum_6m_pct = None
        if len(prices) >= 126:
            price_126d_ago = prices[-126]
            current_price = prices[-1]
            if price_126d_ago and current_price and price_126d_ago > 0:
                momentum_6m_pct = ((current_price - price_126d_ago) / price_126d_ago) * 100
                logging.info(f"{symbol}: 6M momentum = {momentum_6m_pct:.2f}%")

        # Normalize: -40% to +80% maps to 0-100
        momentum_6m_normalized = normalize_metric(momentum_6m_pct, -40, 80)

        # --- 2.3: JT Momentum 12-1 (252 to 21 trading days ago) ---
        # Classic momentum indicator that excludes the most recent month
        # to avoid short-term reversals
        jt_momentum_pct = None
        if len(prices) >= 252:
            price_252d_ago = prices[-252]
            price_21d_ago = prices[-21]
            if price_252d_ago and price_21d_ago and price_252d_ago > 0:
                jt_momentum_pct = ((price_21d_ago - price_252d_ago) / price_252d_ago) * 100
                logging.info(f"{symbol}: JT 12-1 momentum = {jt_momentum_pct:.2f}%")

        # Normalize: -50% to +100% maps to 0-100
        jt_momentum_normalized = normalize_metric(jt_momentum_pct, -50, 100)

        # --- 2.4: Risk-Adjusted Momentum (Momentum / Volatility) ---
        # Calculate volatility (standard deviation of returns)
        risk_adjusted_pct = None
        if len(prices) >= 63:
            # Calculate daily returns for last 63 days
            recent_prices = prices[-63:]
            returns = []
            for i in range(1, len(recent_prices)):
                if recent_prices[i-1] and recent_prices[i] and recent_prices[i-1] > 0:
                    daily_return = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
                    returns.append(daily_return)

            if len(returns) >= 20:
                volatility = np.std(returns) * np.sqrt(252)  # Annualized volatility

                if volatility > 0 and momentum_3m_pct is not None:
                    # Risk-adjusted momentum = momentum / volatility (Sharpe-style)
                    # Multiply by 100 to get percentage-like values
                    risk_adjusted_pct = (momentum_3m_pct / (volatility * 100)) * 100
                    logging.info(f"{symbol}: Risk-adjusted momentum = {risk_adjusted_pct:.2f}")

        # Normalize: -50 to +50 maps to 0-100
        risk_adjusted_normalized = normalize_metric(risk_adjusted_pct, -50, 50)

        # ========== STEP 3: Calculate Composite Momentum Score ==========
        # Weighted average: 3M 20%, 6M 20%, JT 25%, Risk-Adjusted 20%, Strength 15%
        components = []
        weights = []

        if momentum_3m_normalized is not None:
            components.append(momentum_3m_normalized * 0.20)
            weights.append(0.20)

        if momentum_6m_normalized is not None:
            components.append(momentum_6m_normalized * 0.20)
            weights.append(0.20)

        if jt_momentum_normalized is not None:
            components.append(jt_momentum_normalized * 0.25)
            weights.append(0.25)

        if risk_adjusted_normalized is not None:
            components.append(risk_adjusted_normalized * 0.20)
            weights.append(0.20)

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
            jt_momentum_normalized,
            momentum_3m_normalized,
            momentum_6m_normalized,
            risk_adjusted_normalized,
        )
        records.append(record)

        # ========== STEP 4: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO momentum_metrics
                (symbol, date, momentum_strength, jt_momentum_12_1,
                 momentum_3m, momentum_6m, risk_adjusted_momentum)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    momentum_strength = EXCLUDED.momentum_strength,
                    jt_momentum_12_1 = EXCLUDED.jt_momentum_12_1,
                    momentum_3m = EXCLUDED.momentum_3m,
                    momentum_6m = EXCLUDED.momentum_6m,
                    risk_adjusted_momentum = EXCLUDED.risk_adjusted_momentum,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                records,
            )
            conn.commit()
            logging.info(f"✅ {symbol}: Inserted {len(records)} momentum metric records")

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
    logging.info("Momentum Metrics Loader - Starting")
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
    logging.info(f"✅ Momentum Metrics Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
