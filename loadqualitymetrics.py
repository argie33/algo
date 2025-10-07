#!/usr/bin/env python3
# Updated: 2025-10-07 - Quality Metrics Calculator
"""
Quality Metrics Loader

Calculates comprehensive quality metrics for stocks based on:
- Profitability consistency (from quarterly financials)
- Growth quality (sustainable vs volatile growth)
- Financial strength (balance sheet health)

Methodology:
- Profitability Score: 40% - Consistent earnings and margins
- Consistency Score: 30% - Low volatility in key metrics
- Growth Quality: 30% - Sustainable growth patterns

Output:
- quality_metrics table with quality_score (composite score)
- profitability_score (normalized profitability metrics)
- consistency_score (normalized volatility metrics)
- growth_quality (normalized growth sustainability)
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


def calculate_coefficient_of_variation(values):
    """
    Calculate coefficient of variation (CV) for a list of values.
    CV = (standard deviation / mean) * 100

    Lower CV indicates more consistency (better quality).
    Returns None if insufficient data or invalid values.
    """
    valid_values = [v for v in values if v is not None and not np.isnan(v) and not np.isinf(v)]

    if len(valid_values) < 2:
        return None

    mean_val = np.mean(valid_values)
    if mean_val == 0:
        return None

    std_val = np.std(valid_values)
    cv = (std_val / abs(mean_val)) * 100

    return cv


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

    # Drop and recreate quality_metrics table
    logging.info("Creating quality_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS quality_metrics;")
    cursor.execute(
        """
        CREATE TABLE quality_metrics (
            symbol                      VARCHAR(50),
            date                        DATE,
            quality_score               DOUBLE PRECISION,  -- Composite quality score (0-100)
            profitability_score         DOUBLE PRECISION,  -- Profitability consistency normalized
            consistency_score           DOUBLE PRECISION,  -- Low volatility in metrics normalized
            growth_quality              DOUBLE PRECISION,  -- Sustainable growth normalized
            fetched_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """
    )

    # Create indexes for query performance
    logging.info("Creating indexes on quality_metrics...")
    cursor.execute("CREATE INDEX idx_quality_metrics_symbol ON quality_metrics(symbol);")
    cursor.execute("CREATE INDEX idx_quality_metrics_date ON quality_metrics(date DESC);")
    conn.commit()
    logging.info("Indexes created successfully")

    logging.info("Table 'quality_metrics' ready.")

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
    Process a single symbol and calculate quality metrics

    Calculates:
    1. Profitability score from consistent margins and ROE
    2. Consistency score from low volatility in earnings and revenue
    3. Growth quality from sustainable growth patterns

    Args:
        symbol: Stock symbol to process
        conn_pool: Database connection pool

    Returns:
        int: Number of records inserted
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing quality metrics for {symbol}...")

        # ========== STEP 1: Fetch Quarterly Financial Data ==========
        # Get last 8 quarters for trend analysis
        cursor.execute(
            """
            SELECT
                quarter,
                net_income,
                total_revenue,
                gross_profit,
                operating_income
            FROM quarterly_income_statement
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 8
            """,
            (symbol,),
        )
        income_data = cursor.fetchall()
        logging.info(f"{symbol}: Found {len(income_data)} quarterly income records")

        # ========== STEP 2: Fetch Key Metrics (Current) ==========
        cursor.execute(
            """
            SELECT
                return_on_equity_pct,
                return_on_assets_pct,
                profit_margin_pct,
                operating_margin_pct,
                gross_margin_pct
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        metrics_row = cursor.fetchone()
        logging.info(f"{symbol}: Metrics row: {metrics_row}")

        # ========== STEP 3: Fetch Balance Sheet for Financial Strength ==========
        cursor.execute(
            """
            SELECT
                total_assets,
                total_liabilities,
                total_equity
            FROM quarterly_balance_sheet
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 4
            """,
            (symbol,),
        )
        balance_data = cursor.fetchall()
        logging.info(f"{symbol}: Found {len(balance_data)} balance sheet records")

        if not income_data and not metrics_row:
            logging.warning(f"No quality data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # ========== STEP 4: Calculate Quality Metrics ==========
        records = []
        current_date = datetime.now().date()

        # --- 4.1: Profitability Score ---
        # Based on current profitability metrics (ROE, margins)
        profitability_components = []

        if metrics_row:
            # NOTE: key_metrics stores percentages as decimals (0.15 = 15%)
            roe = safe_numeric(metrics_row[0])
            roa = safe_numeric(metrics_row[1])
            profit_margin = safe_numeric(metrics_row[2])
            operating_margin = safe_numeric(metrics_row[3])
            gross_margin = safe_numeric(metrics_row[4])

            # Convert decimals to percentages for normalization
            if roe is not None:
                roe_pct = roe * 100
                profitability_components.append(normalize_metric(roe_pct, -10, 40))

            if roa is not None:
                roa_pct = roa * 100
                profitability_components.append(normalize_metric(roa_pct, -5, 25))

            if profit_margin is not None:
                profit_margin_pct = profit_margin * 100
                profitability_components.append(normalize_metric(profit_margin_pct, -10, 30))

            if operating_margin is not None:
                operating_margin_pct = operating_margin * 100
                profitability_components.append(normalize_metric(operating_margin_pct, -10, 35))

        profitability_score = None
        if profitability_components:
            profitability_score = np.mean(profitability_components)
            logging.info(f"{symbol}: Profitability score = {profitability_score:.2f}")

        # --- 4.2: Consistency Score ---
        # Lower volatility in earnings and revenue = higher quality
        consistency_components = []

        if len(income_data) >= 4:
            # Calculate revenue volatility (coefficient of variation)
            revenues = [safe_numeric(row[2]) for row in income_data]
            revenue_cv = calculate_coefficient_of_variation(revenues)

            # Calculate earnings volatility
            net_incomes = [safe_numeric(row[1]) for row in income_data]
            earnings_cv = calculate_coefficient_of_variation(net_incomes)

            # Lower CV = higher consistency score
            # CV of 0-50% is good (maps to 100-50), CV >100% is poor (maps to <0)
            if revenue_cv is not None:
                revenue_consistency = normalize_metric(revenue_cv, 0, 100)
                # Invert: lower CV should give higher score
                revenue_consistency = 100 - revenue_consistency
                consistency_components.append(revenue_consistency)

            if earnings_cv is not None:
                earnings_consistency = normalize_metric(earnings_cv, 0, 150)
                # Invert: lower CV should give higher score
                earnings_consistency = 100 - earnings_consistency
                consistency_components.append(earnings_consistency)

        consistency_score = None
        if consistency_components:
            consistency_score = np.mean(consistency_components)
            logging.info(f"{symbol}: Consistency score = {consistency_score:.2f}")

        # --- 4.3: Growth Quality Score ---
        # Sustainable growth: positive revenue/earnings trend with low volatility
        growth_quality_components = []

        if len(income_data) >= 4:
            # Check for positive revenue trend
            recent_revenues = [safe_numeric(row[2]) for row in income_data[:4]]
            if all(r is not None for r in recent_revenues):
                # Compare recent average to older average
                recent_avg = np.mean(recent_revenues)
                older_revenues = [safe_numeric(row[2]) for row in income_data[4:]]
                if older_revenues and all(r is not None for r in older_revenues):
                    older_avg = np.mean(older_revenues)
                    if older_avg > 0:
                        revenue_growth_trend = ((recent_avg - older_avg) / older_avg) * 100
                        growth_quality_components.append(normalize_metric(revenue_growth_trend, -20, 40))

            # Check for positive earnings trend
            recent_earnings = [safe_numeric(row[1]) for row in income_data[:4]]
            if all(e is not None for e in recent_earnings):
                recent_avg_earnings = np.mean(recent_earnings)
                older_earnings = [safe_numeric(row[1]) for row in income_data[4:]]
                if older_earnings and all(e is not None for e in older_earnings):
                    older_avg_earnings = np.mean(older_earnings)
                    if older_avg_earnings != 0:
                        earnings_growth_trend = ((recent_avg_earnings - older_avg_earnings) / abs(older_avg_earnings)) * 100
                        growth_quality_components.append(normalize_metric(earnings_growth_trend, -30, 50))

        # Add balance sheet strength (equity ratio)
        if len(balance_data) >= 1:
            assets = safe_numeric(balance_data[0][0])
            equity = safe_numeric(balance_data[0][2])

            if assets and equity and assets > 0:
                equity_ratio = (equity / assets) * 100
                # Higher equity ratio = better quality (20-80% is typical range)
                growth_quality_components.append(normalize_metric(equity_ratio, 10, 80))

        growth_quality = None
        if growth_quality_components:
            growth_quality = np.mean(growth_quality_components)
            logging.info(f"{symbol}: Growth quality = {growth_quality:.2f}")

        # ========== STEP 5: Calculate Composite Quality Score ==========
        # Weighted average: Profitability 40%, Consistency 30%, Growth Quality 30%
        components = []
        weights = []

        if profitability_score is not None:
            components.append(profitability_score * 0.40)
            weights.append(0.40)

        if consistency_score is not None:
            components.append(consistency_score * 0.30)
            weights.append(0.30)

        if growth_quality is not None:
            components.append(growth_quality * 0.30)
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
            profitability_score,
            consistency_score,
            growth_quality,
        )
        records.append(record)

        # ========== STEP 6: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO quality_metrics
                (symbol, date, quality_score, profitability_score,
                 consistency_score, growth_quality)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    quality_score = EXCLUDED.quality_score,
                    profitability_score = EXCLUDED.profitability_score,
                    consistency_score = EXCLUDED.consistency_score,
                    growth_quality = EXCLUDED.growth_quality,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                records,
            )
            conn.commit()
            logging.info(f"✅ {symbol}: Inserted {len(records)} quality metric records")

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
    logging.info("Quality Metrics Loader - Starting")
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
    logging.info(f"✅ Quality Metrics Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
