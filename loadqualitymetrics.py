#!/usr/bin/env python3
# Updated: 2025-10-16 14:46 - Trigger rebuild: 20251016_144600 - Populate quality metrics to AWS
"""
Quality Metrics Loader - Professional Quality Factor Inputs

Calculates 13 industry-standard quality metrics:

1. PROFITABILITY (5 metrics):
   - ROE, ROA, Gross Margin, Operating Margin, Profit Margin

2. CASH QUALITY (2 metrics):
   - FCF/Net Income, Operating CF/Net Income

3. BALANCE SHEET STRENGTH (3 metrics):
   - Debt/Equity, Current Ratio, Quick Ratio

4. EARNINGS QUALITY (2 metrics):
   - Earnings Surprise Average, EPS Growth Stability

5. CAPITAL ALLOCATION (1 metric):
   - Payout Ratio

All metrics pulled from existing tables (key_metrics, earnings_metrics).
NO scores calculated here - just raw inputs for scoring engine.
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
import psycopg2
import psycopg2.extensions
from psycopg2 import pool
from psycopg2.extras import execute_values

# Register numpy type adapters
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)

MAX_WORKERS = min(os.cpu_count() or 1, 4)
DB_POOL_MIN = 2
DB_POOL_MAX = 10


def get_db_config():
    """Fetch database credentials"""
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
    return (sec["username"], sec["password"], sec["host"], int(sec["port"]), sec["dbname"])


def safe_numeric(value):
    """Safely convert value to float"""
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
    """Initialize database and create quality_metrics table with 13 inputs"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cursor.execute(
        "INSERT INTO last_updated (script_name, last_run) VALUES (%s, CURRENT_TIMESTAMP) "
        "ON CONFLICT (script_name) DO UPDATE SET last_run = CURRENT_TIMESTAMP;",
        (SCRIPT_NAME,),
    )
    conn.commit()

    # Drop and recreate with 13 professional quality inputs
    logging.info("Creating quality_metrics table with 13 professional inputs...")
    cursor.execute("DROP TABLE IF EXISTS quality_metrics;")
    cursor.execute(
        """
        CREATE TABLE quality_metrics (
            symbol                          VARCHAR(50),
            date                            DATE,

            -- PROFITABILITY (5 metrics from key_metrics)
            return_on_equity_pct            DOUBLE PRECISION,
            return_on_assets_pct            DOUBLE PRECISION,
            gross_margin_pct                DOUBLE PRECISION,
            operating_margin_pct            DOUBLE PRECISION,
            profit_margin_pct               DOUBLE PRECISION,

            -- CASH QUALITY (2 metrics)
            fcf_to_net_income               DOUBLE PRECISION,
            operating_cf_to_net_income      DOUBLE PRECISION,

            -- BALANCE SHEET STRENGTH (3 metrics from key_metrics)
            debt_to_equity                  DOUBLE PRECISION,
            current_ratio                   DOUBLE PRECISION,
            quick_ratio                     DOUBLE PRECISION,

            -- EARNINGS QUALITY (2 metrics from earnings_metrics)
            earnings_surprise_avg           DOUBLE PRECISION,
            eps_growth_stability            DOUBLE PRECISION,

            -- CAPITAL ALLOCATION (1 metric from key_metrics)
            payout_ratio                    DOUBLE PRECISION,

            fetched_at                      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """
    )

    logging.info("Creating indexes...")
    cursor.execute("CREATE INDEX idx_quality_metrics_symbol ON quality_metrics(symbol);")
    cursor.execute("CREATE INDEX idx_quality_metrics_date ON quality_metrics(date DESC);")
    conn.commit()
    logging.info("Table 'quality_metrics' ready with 13 professional inputs")

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
        DB_POOL_MIN, DB_POOL_MAX, host=host, port=port, user=user, password=pwd, dbname=db
    )


def process_symbol(symbol, conn_pool):
    """
    Calculate 13 professional quality inputs for a symbol

    Returns:
        int: Number of records inserted
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing quality inputs for {symbol}...")
        current_date = datetime.now().date()

        # ========== PROFITABILITY + BALANCE SHEET + CASH (from key_metrics) ==========
        cursor.execute(
            """
            SELECT
                return_on_equity_pct,           -- 0
                return_on_assets_pct,           -- 1
                gross_margin_pct,               -- 2
                operating_margin_pct,           -- 3
                profit_margin_pct,              -- 4
                debt_to_equity,                 -- 5
                current_ratio,                  -- 6
                quick_ratio,                    -- 7
                payout_ratio,                   -- 8
                free_cashflow,                  -- 9
                operating_cashflow,             -- 10
                net_income,                     -- 11
                gross_profit,                   -- 12
                total_revenue,                  -- 13
                dividend_rate,                  -- 14
                eps_trailing                    -- 15
            FROM key_metrics
            WHERE ticker = %s
            LIMIT 1
            """,
            (symbol,),
        )
        km = cursor.fetchone()

        # Extract metrics from key_metrics
        roe = safe_numeric(km[0]) if km else None
        roa = safe_numeric(km[1]) if km else None
        gross_margin = safe_numeric(km[2]) if km else None
        operating_margin = safe_numeric(km[3]) if km else None
        profit_margin = safe_numeric(km[4]) if km else None
        debt_equity = safe_numeric(km[5]) if km else None
        current_ratio = safe_numeric(km[6]) if km else None
        quick_ratio = safe_numeric(km[7]) if km else None
        payout_ratio = safe_numeric(km[8]) if km else None

        fcf = safe_numeric(km[9]) if km else None
        op_cf = safe_numeric(km[10]) if km else None
        net_income = safe_numeric(km[11]) if km else None

        # Calculate gross_margin if NULL but raw data available
        if gross_margin is None and km:
            gross_profit = safe_numeric(km[12])
            total_revenue = safe_numeric(km[13])
            if gross_profit is not None and total_revenue and total_revenue != 0:
                gross_margin = gross_profit / total_revenue

        # Calculate payout_ratio if NULL but raw data available
        if payout_ratio is None and km:
            dividend_rate = safe_numeric(km[14])
            eps_trailing = safe_numeric(km[15])
            if dividend_rate is not None and eps_trailing and eps_trailing != 0:
                payout_ratio = dividend_rate / eps_trailing

        # Calculate cash quality ratios from key_metrics (yfinance single source)
        fcf_to_ni = None
        if fcf is not None and net_income and net_income != 0:
            fcf_to_ni = fcf / net_income

        op_cf_to_ni = None
        if op_cf is not None and net_income and net_income != 0:
            op_cf_to_ni = op_cf / net_income

        # ========== EARNINGS QUALITY (from earnings_metrics) ==========
        # Get last 4 quarters of earnings quality data for consistency metrics
        cursor.execute(
            """
            SELECT
                earnings_surprise_pct,
                eps_yoy_growth
            FROM earnings_metrics
            WHERE symbol = %s
            ORDER BY report_date DESC
            LIMIT 4
            """,
            (symbol,),
        )
        earnings_data = cursor.fetchall()

        earnings_surprise_avg = None
        eps_growth_stability = None

        if earnings_data and len(earnings_data) >= 2:
            # Earnings surprise average (last 4 quarters)
            surprises = [safe_numeric(row[0]) for row in earnings_data if row[0] is not None]
            if surprises:
                earnings_surprise_avg = np.mean(surprises)

            # EPS growth stability (stddev of YoY growth rates)
            eps_yoy = [safe_numeric(row[1]) for row in earnings_data if row[1] is not None]
            if len(eps_yoy) >= 2:
                eps_growth_stability = np.std(eps_yoy)

        # ========== CREATE RECORD ==========
        record = (
            symbol,
            current_date,
            # Profitability
            roe,
            roa,
            gross_margin,
            operating_margin,
            profit_margin,
            # Cash Quality
            fcf_to_ni,
            op_cf_to_ni,
            # Balance Sheet
            debt_equity,
            current_ratio,
            quick_ratio,
            # Earnings Quality
            earnings_surprise_avg,
            eps_growth_stability,
            # Capital Allocation
            payout_ratio,
        )

        # ========== INSERT ==========
        execute_values(
            cursor,
            """
            INSERT INTO quality_metrics
            (symbol, date,
             return_on_equity_pct, return_on_assets_pct, gross_margin_pct,
             operating_margin_pct, profit_margin_pct,
             fcf_to_net_income, operating_cf_to_net_income,
             debt_to_equity, current_ratio, quick_ratio,
             earnings_surprise_avg, eps_growth_stability,
             payout_ratio)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                return_on_equity_pct = EXCLUDED.return_on_equity_pct,
                return_on_assets_pct = EXCLUDED.return_on_assets_pct,
                gross_margin_pct = EXCLUDED.gross_margin_pct,
                operating_margin_pct = EXCLUDED.operating_margin_pct,
                profit_margin_pct = EXCLUDED.profit_margin_pct,
                fcf_to_net_income = EXCLUDED.fcf_to_net_income,
                operating_cf_to_net_income = EXCLUDED.operating_cf_to_net_income,
                debt_to_equity = EXCLUDED.debt_to_equity,
                current_ratio = EXCLUDED.current_ratio,
                quick_ratio = EXCLUDED.quick_ratio,
                earnings_surprise_avg = EXCLUDED.earnings_surprise_avg,
                eps_growth_stability = EXCLUDED.eps_growth_stability,
                payout_ratio = EXCLUDED.payout_ratio,
                fetched_at = CURRENT_TIMESTAMP
            """,
            [record],
        )
        conn.commit()
        logging.info(f"✅ {symbol}: Inserted 13 quality inputs")

        conn_pool.putconn(conn)
        return 1

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        try:
            conn_pool.putconn(conn)
        except:
            pass
        return 0


def main():
    """Main execution"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Quality Metrics Loader - Professional 13 Inputs")
    logging.info("=" * 80)

    symbols = initialize_db()
    conn_pool = create_connection_pool()

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
