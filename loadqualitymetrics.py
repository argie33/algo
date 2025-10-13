#!/usr/bin/env python3
# Updated: 2025-10-13 - Quality Metrics Calculator (AWS deployment - fixed container names)
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

            -- RAW calculated metrics ONLY (for stockscores script to use)
            accruals_ratio              DOUBLE PRECISION,  -- (Net Income - Op Cash Flow) / Total Assets
            fcf_to_net_income           DOUBLE PRECISION,  -- Free Cash Flow / Net Income
            debt_to_equity              DOUBLE PRECISION,  -- Total Liabilities / Total Equity
            current_ratio               DOUBLE PRECISION,  -- Current Assets / Current Liabilities
            interest_coverage           DOUBLE PRECISION,  -- Operating Income / Interest Expense
            asset_turnover              DOUBLE PRECISION,  -- Revenue / Avg Total Assets

            -- NOTE: ROE, ROA, margins already in key_metrics
            -- NOTE: Scores calculated by stockscores script, not here

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

    Industry-standard approach:
    1. Profitability (40%): ROE, ROA, margins from key_metrics
    2. Earnings Quality (30%): Accruals ratio, FCF/Net Income
    3. Financial Stability (20%): Debt/Equity, Current Ratio, Interest Coverage
    4. Operational Efficiency (10%): Asset Turnover

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

        # ========== STEP 1: Fetch Key Metrics (from ticker.info data) ==========
        cursor.execute(
            """
            SELECT
                return_on_equity_pct,
                return_on_assets_pct,
                profit_margin_pct,
                operating_margin_pct,
                gross_margin_pct,
                current_ratio,
                debt_to_equity,
                free_cashflow,
                net_income
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        metrics_row = cursor.fetchone()
        logging.info(f"{symbol}: Key metrics row: {metrics_row}")

        # ========== STEP 2: Fetch Latest Quarter Financial Data ==========
        # Get most recent quarter data using item_name/value structure
        cursor.execute(
            """
            SELECT DISTINCT date FROM quarterly_income_statement
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 2
            """,
            (symbol,),
        )
        quarter_dates = [row[0] for row in cursor.fetchall()]
        logging.info(f"{symbol}: Found {len(quarter_dates)} recent quarters")

        financial_data = []
        for qdate in quarter_dates:
            # Get all metrics for this quarter
            cursor.execute(
                """
                SELECT
                    MAX(CASE WHEN item_name = 'Net Income' THEN value END) as net_income,
                    MAX(CASE WHEN item_name = 'Revenue' THEN value END) as total_revenue,
                    MAX(CASE WHEN item_name = 'Operating Income' THEN value END) as operating_income,
                    MAX(CASE WHEN item_name = 'Interest Expense' THEN value END) as interest_expense
                FROM quarterly_income_statement
                WHERE symbol = %s AND date = %s
                """,
                (symbol, qdate),
            )
            income = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    MAX(CASE WHEN item_name = 'Total Assets' THEN value END) as total_assets,
                    MAX(CASE WHEN item_name = 'Total Liabilities' THEN value END) as total_liabilities,
                    MAX(CASE WHEN item_name = 'Total Equity' THEN value END) as total_equity,
                    MAX(CASE WHEN item_name = 'Current Assets' THEN value END) as current_assets,
                    MAX(CASE WHEN item_name = 'Current Liabilities' THEN value END) as current_liabilities
                FROM quarterly_balance_sheet
                WHERE symbol = %s AND date = %s
                """,
                (symbol, qdate),
            )
            balance = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    MAX(CASE WHEN item_name = 'Operating Cash Flow' THEN value END) as operating_cash_flow,
                    MAX(CASE WHEN item_name = 'Free Cash Flow' THEN value END) as free_cash_flow
                FROM quarterly_cash_flow
                WHERE symbol = %s AND date = %s
                """,
                (symbol, qdate),
            )
            cashflow = cursor.fetchone()

            # Combine into single tuple
            if income and balance and cashflow:
                financial_data.append((
                    qdate,  # 0
                    income[0],  # 1: net_income
                    income[1],  # 2: total_revenue
                    income[2],  # 3: operating_income
                    income[3],  # 4: interest_expense
                    balance[0],  # 5: total_assets
                    balance[1],  # 6: total_liabilities
                    balance[2],  # 7: total_equity
                    balance[3],  # 8: current_assets
                    balance[4],  # 9: current_liabilities
                    cashflow[0],  # 10: operating_cash_flow
                    cashflow[1],  # 11: free_cash_flow
                ))

        logging.info(f"{symbol}: Assembled {len(financial_data)} quarters of complete financial data")

        if not metrics_row and not financial_data:
            logging.warning(f"No quality data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # ========== STEP 3: Calculate Metrics (prefer key_metrics, fallback to quarterly) ==========
        current_date = datetime.now().date()

        # Initialize metrics - try to get from key_metrics first
        current_ratio = safe_numeric(metrics_row[5]) if metrics_row and len(metrics_row) > 5 else None
        debt_to_equity = safe_numeric(metrics_row[6]) if metrics_row and len(metrics_row) > 6 else None
        km_free_cashflow = safe_numeric(metrics_row[7]) if metrics_row and len(metrics_row) > 7 else None
        km_net_income = safe_numeric(metrics_row[8]) if metrics_row and len(metrics_row) > 8 else None

        # Calculate FCF to Net Income from key_metrics if available
        fcf_to_net_income = None
        if km_free_cashflow is not None and km_net_income and km_net_income != 0:
            fcf_to_net_income = km_free_cashflow / km_net_income

        # These must be calculated from quarterly statements
        accruals_ratio = None
        interest_coverage = None
        asset_turnover = None

        if financial_data and len(financial_data) > 0:
            latest = financial_data[0]
            net_income = safe_numeric(latest[1])
            total_revenue = safe_numeric(latest[2])
            operating_income = safe_numeric(latest[3])
            interest_expense = safe_numeric(latest[4])
            total_assets = safe_numeric(latest[5])
            total_liabilities = safe_numeric(latest[6])
            total_equity = safe_numeric(latest[7])
            current_assets = safe_numeric(latest[8])
            current_liabilities = safe_numeric(latest[9])
            operating_cash_flow = safe_numeric(latest[10])
            free_cash_flow = safe_numeric(latest[11])

            # Accruals Ratio = (Net Income - Operating Cash Flow) / Total Assets
            if net_income is not None and operating_cash_flow is not None and total_assets and total_assets > 0:
                accruals_ratio = (net_income - operating_cash_flow) / total_assets

            # Fallback: FCF / Net Income from quarterly if not from key_metrics
            if fcf_to_net_income is None and free_cash_flow is not None and net_income and net_income != 0:
                fcf_to_net_income = free_cash_flow / net_income

            # Fallback: Debt to Equity from quarterly if not from key_metrics
            if debt_to_equity is None and total_liabilities is not None and total_equity and total_equity > 0:
                debt_to_equity = total_liabilities / total_equity

            # Fallback: Current Ratio from quarterly if not from key_metrics
            if current_ratio is None and current_assets is not None and current_liabilities and current_liabilities > 0:
                current_ratio = current_assets / current_liabilities

            # Interest Coverage = Operating Income / Interest Expense
            if operating_income is not None and interest_expense and interest_expense != 0:
                interest_coverage = operating_income / abs(interest_expense)

            # Asset Turnover (use average of last 2 quarters if available)
            if total_revenue is not None and total_assets and total_assets > 0:
                if len(financial_data) >= 2:
                    assets_prev = safe_numeric(financial_data[1][5])
                    avg_assets = (total_assets + assets_prev) / 2 if assets_prev else total_assets
                else:
                    avg_assets = total_assets
                asset_turnover = (total_revenue * 4) / avg_assets if avg_assets > 0 else None  # Annualize revenue

        # Create record with RAW metrics ONLY - no scores
        record = (
            symbol,
            current_date,
            accruals_ratio,
            fcf_to_net_income,
            debt_to_equity,
            current_ratio,
            interest_coverage,
            asset_turnover,
        )
        records = [record]

        # ========== STEP 4: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO quality_metrics
                (symbol, date, accruals_ratio, fcf_to_net_income, debt_to_equity,
                 current_ratio, interest_coverage, asset_turnover)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    accruals_ratio = EXCLUDED.accruals_ratio,
                    fcf_to_net_income = EXCLUDED.fcf_to_net_income,
                    debt_to_equity = EXCLUDED.debt_to_equity,
                    current_ratio = EXCLUDED.current_ratio,
                    interest_coverage = EXCLUDED.interest_coverage,
                    asset_turnover = EXCLUDED.asset_turnover,
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
