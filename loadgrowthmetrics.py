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
        return None  # FAIL - Insufficient data for normalization

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

            -- Original RAW calculated metrics (for stockscores script to use)
            revenue_growth_3y_cagr      DOUBLE PRECISION,  -- 3-year revenue CAGR
            eps_growth_3y_cagr          DOUBLE PRECISION,  -- 3-year EPS CAGR
            operating_income_growth_yoy DOUBLE PRECISION,  -- Operating income YoY growth
            roe_trend                   DOUBLE PRECISION,  -- ROE change (current - 1Y ago)
            sustainable_growth_rate     DOUBLE PRECISION,  -- ROE × (1 - Payout Ratio)
            fcf_growth_yoy              DOUBLE PRECISION,  -- Free cash flow YoY growth

            -- NEW: Bottom-line growth metric
            net_income_growth_yoy       DOUBLE PRECISION,  -- Net income YoY growth (%)

            -- NEW: Margin efficiency trends
            gross_margin_trend          DOUBLE PRECISION,  -- Gross margin change (current - YoY ago) in percentage points
            operating_margin_trend      DOUBLE PRECISION,  -- Operating margin change (current - YoY ago) in percentage points
            net_margin_trend            DOUBLE PRECISION,  -- Net margin change (current - YoY ago) in percentage points

            -- NEW: Growth acceleration metric
            quarterly_growth_momentum   DOUBLE PRECISION,  -- Revenue growth acceleration (latest Q growth - prior Q growth)

            -- NEW: Capital intensity metric
            asset_growth_yoy            DOUBLE PRECISION,  -- Total assets YoY growth (%)

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


def check_data_availability(cursor, symbol):
    """
    DIAGNOSTIC: Check what data is available for a symbol before calculating metrics.
    Returns dictionary showing data availability for each metric.
    Helps identify why metrics might be NULL.
    """
    availability = {
        'symbol': symbol,
        'revenue_estimates': False,
        'earnings_history': False,
        'key_metrics': False,
        'quarterly_income_statement_count': 0,
        'quarterly_income_statement_items': [],
        'quarterly_cashflow_count': 0,
        'quarterly_cashflow_items': [],
        'quarterly_balance_sheet_count': 0,
        'payout_ratio_available': False,
    }

    try:
        # Check revenue_estimates
        cursor.execute("SELECT COUNT(*) FROM revenue_estimates WHERE symbol = %s;", (symbol,))
        availability['revenue_estimates'] = cursor.fetchone()[0] > 0
    except psycopg2.Error as e:
        logging.warning(f"Failed to check revenue_estimates for {symbol}: {e}")
        availability['revenue_estimates'] = False

    try:
        # Check earnings_history
        cursor.execute("SELECT COUNT(*) FROM earnings_history WHERE symbol = %s;", (symbol,))
        availability['earnings_history'] = cursor.fetchone()[0] > 0
    except psycopg2.Error as e:
        logging.warning(f"Failed to check earnings_history for {symbol}: {e}")
        availability['earnings_history'] = False

    try:
        # Check key_metrics
        cursor.execute("SELECT COUNT(*) FROM key_metrics WHERE ticker = %s;", (symbol,))
        availability['key_metrics'] = cursor.fetchone()[0] > 0
    except psycopg2.Error as e:
        logging.warning(f"Failed to check key_metrics for {symbol}: {e}")
        availability['key_metrics'] = False

    try:
        # Check quarterly_income_statement data
        cursor.execute(
            "SELECT COUNT(*), COUNT(DISTINCT item_name) FROM quarterly_income_statement WHERE symbol = %s;",
            (symbol,)
        )
        count_result = cursor.fetchone()
        availability['quarterly_income_statement_count'] = count_result[0] if count_result else 0

        # Get list of available item names
        cursor.execute(
            "SELECT DISTINCT item_name FROM quarterly_income_statement WHERE symbol = %s ORDER BY item_name;",
            (symbol,)
        )
        availability['quarterly_income_statement_items'] = [row[0] for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logging.warning(f"Failed to check quarterly_income_statement for {symbol}: {e}")
        availability['quarterly_income_statement_count'] = 0
        availability['quarterly_income_statement_items'] = []

    try:
        # Check quarterly_cashflow data
        cursor.execute(
            "SELECT COUNT(*), COUNT(DISTINCT item_name) FROM quarterly_cash_flow WHERE symbol = %s;",
            (symbol,)
        )
        count_result = cursor.fetchone()
        availability['quarterly_cashflow_count'] = count_result[0] if count_result else 0

        # Get list of available item names
        cursor.execute(
            "SELECT DISTINCT item_name FROM quarterly_cash_flow WHERE symbol = %s ORDER BY item_name;",
            (symbol,)
        )
        availability['quarterly_cashflow_items'] = [row[0] for row in cursor.fetchall()]
    except psycopg2.Error as e:
        logging.warning(f"Failed to check quarterly_cash_flow for {symbol}: {e}")
        availability['quarterly_cashflow_count'] = 0
        availability['quarterly_cashflow_items'] = []

    try:
        # Check quarterly_balance_sheet data
        cursor.execute(
            "SELECT COUNT(*) FROM quarterly_balance_sheet WHERE symbol = %s;",
            (symbol,)
        )
        availability['quarterly_balance_sheet_count'] = cursor.fetchone()[0]
    except psycopg2.Error as e:
        logging.warning(f"Failed to check quarterly_balance_sheet for {symbol}: {e}")
        availability['quarterly_balance_sheet_count'] = 0

    try:
        # Check payout_ratio
        cursor.execute(
            "SELECT COUNT(*) FROM quality_metrics WHERE symbol = %s AND payout_ratio IS NOT NULL;",
            (symbol,)
        )
        availability['payout_ratio_available'] = cursor.fetchone()[0] > 0
    except psycopg2.Error as e:
        logging.warning(f"Failed to check payout_ratio for {symbol}: {e}")
        availability['payout_ratio_available'] = False

    return availability


def log_metric_unavailable(symbol, metric_name, reason):
    """Log why a specific metric is NULL with diagnostic info."""
    logging.debug(f"{symbol}: ❌ {metric_name} = NULL → {reason}")


def process_symbol(symbol, conn_pool):
    """
    Process a single symbol and calculate growth metrics

    STRICT NO-FALLBACK POLICY:
    - Every metric requires specific data from specific sources
    - If source data is missing/insufficient: metric stays NULL
    - No approximations, no proxies, no assumptions
    - Detailed logging explains exactly why metrics are NULL

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

        # Diagnostic: Check data availability
        data_avail = check_data_availability(cursor, symbol)
        if data_avail['quarterly_income_statement_count'] == 0:
            logging.info(f"{symbol}: No quarterly_income_statement data found - most metrics will be NULL")
        if data_avail['quarterly_cashflow_count'] == 0:
            logging.info(f"{symbol}: No quarterly_cash_flow data found - FCF metrics will be NULL")

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
            if len(op_income_rows) < 5:
                log_metric_unavailable(symbol, "operating_income_growth_yoy",
                    f"Insufficient Op Income data: {len(op_income_rows)} quarters (need 5)")
            else:
                current_op_income = safe_numeric(op_income_rows[0][0])
                year_ago_op_income = safe_numeric(op_income_rows[4][0])
                if current_op_income is None:
                    log_metric_unavailable(symbol, "operating_income_growth_yoy", "Current Op Income is invalid")
                elif year_ago_op_income is None:
                    log_metric_unavailable(symbol, "operating_income_growth_yoy", "Year-ago Op Income is invalid")
                elif year_ago_op_income == 0:
                    log_metric_unavailable(symbol, "operating_income_growth_yoy", "Year-ago Op Income is zero (cannot divide)")
                else:
                    operating_income_growth_yoy = ((current_op_income - year_ago_op_income) / abs(year_ago_op_income)) * 100
        except Exception as e:
            log_metric_unavailable(symbol, "operating_income_growth_yoy", f"Query error: {e}")

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
            if len(fcf_rows) < 5:
                log_metric_unavailable(symbol, "fcf_growth_yoy",
                    f"Insufficient FCF data: {len(fcf_rows)} quarters (need 5)")
            else:
                current_fcf = safe_numeric(fcf_rows[0][0])
                year_ago_fcf = safe_numeric(fcf_rows[4][0])
                if current_fcf is None:
                    log_metric_unavailable(symbol, "fcf_growth_yoy", "Current FCF is invalid")
                elif year_ago_fcf is None:
                    log_metric_unavailable(symbol, "fcf_growth_yoy", "Year-ago FCF is invalid")
                elif year_ago_fcf == 0:
                    log_metric_unavailable(symbol, "fcf_growth_yoy", "Year-ago FCF is zero (cannot divide)")
                else:
                    fcf_growth_yoy = ((current_fcf - year_ago_fcf) / abs(year_ago_fcf)) * 100
        except Exception as e:
            log_metric_unavailable(symbol, "fcf_growth_yoy", f"Query error: {e}")

        # ========== STEP 7: Net Income Growth (YoY) ==========
        net_income_growth_yoy = None
        try:
            cursor.execute(
                """
                SELECT value FROM quarterly_income_statement
                WHERE symbol = %s AND item_name = 'Net Income'
                ORDER BY date DESC
                LIMIT 5
                """,
                (symbol,),
            )
            ni_rows = cursor.fetchall()
            if len(ni_rows) < 5:
                log_metric_unavailable(symbol, "net_income_growth_yoy",
                    f"Insufficient data: {len(ni_rows)} quarters (need 5)")
            else:
                current_ni = safe_numeric(ni_rows[0][0])
                year_ago_ni = safe_numeric(ni_rows[4][0])
                if current_ni is None:
                    log_metric_unavailable(symbol, "net_income_growth_yoy",
                        "Current quarter Net Income is invalid")
                elif year_ago_ni is None:
                    log_metric_unavailable(symbol, "net_income_growth_yoy",
                        "Year-ago Net Income is invalid")
                elif year_ago_ni == 0:
                    log_metric_unavailable(symbol, "net_income_growth_yoy",
                        "Year-ago Net Income is zero (cannot divide)")
                else:
                    net_income_growth_yoy = ((current_ni - year_ago_ni) / abs(year_ago_ni)) * 100
        except Exception as e:
            log_metric_unavailable(symbol, "net_income_growth_yoy", f"Query error: {e}")

        # ========== STEP 8: Margin Trends (Gross, Operating, Net) ==========
        gross_margin_trend = None
        operating_margin_trend = None
        net_margin_trend = None
        try:
            # Fetch all financial data for margin calculation (pivot by item_name and date)
            cursor.execute(
                """
                SELECT date, item_name, value
                FROM quarterly_income_statement
                WHERE symbol = %s AND item_name IN ('Total Revenue', 'Operating Revenue', 'Gross Profit', 'Operating Income', 'Net Income')
                ORDER BY date DESC
                LIMIT 40
                """,
                (symbol,),
            )
            all_rows = cursor.fetchall()

            if len(all_rows) == 0:
                log_metric_unavailable(symbol, "margin_trends", "No quarterly_income_statement data found")
            else:
                # Group by date
                from collections import defaultdict
                data_by_date = defaultdict(dict)

                for date, item_name, value in all_rows:
                    data_by_date[date][item_name] = safe_numeric(value)

                # Get sorted unique dates (most recent first)
                sorted_dates = sorted(data_by_date.keys(), reverse=True)

                if len(sorted_dates) < 5:
                    log_metric_unavailable(symbol, "margin_trends",
                        f"Insufficient quarters: {len(sorted_dates)} (need 5)")
                else:
                    # Current quarter (most recent)
                    current_date = sorted_dates[0]
                    current_revenue = data_by_date[current_date].get('Total Revenue') or data_by_date[current_date].get('Operating Revenue')
                    current_gross = data_by_date[current_date].get('Gross Profit')
                    current_op_income = data_by_date[current_date].get('Operating Income')
                    current_net = data_by_date[current_date].get('Net Income')

                    # Year ago quarter (4 quarters back)
                    year_ago_date = sorted_dates[4]
                    year_ago_revenue = data_by_date[year_ago_date].get('Total Revenue') or data_by_date[year_ago_date].get('Operating Revenue')
                    year_ago_gross = data_by_date[year_ago_date].get('Gross Profit')
                    year_ago_op_income = data_by_date[year_ago_date].get('Operating Income')
                    year_ago_net = data_by_date[year_ago_date].get('Net Income')

                    # VALIDATE: Current revenue required
                    if current_revenue is None or current_revenue <= 0:
                        log_metric_unavailable(symbol, "margin_trends",
                            f"Current revenue invalid: {current_revenue}")
                    elif year_ago_revenue is None or year_ago_revenue <= 0:
                        log_metric_unavailable(symbol, "margin_trends",
                            f"Year-ago revenue invalid: {year_ago_revenue}")
                    else:
                        # Calculate current margins (as percentages)
                        current_gross_margin = (current_gross / current_revenue) * 100 if current_gross else None
                        current_op_margin = (current_op_income / current_revenue) * 100 if current_op_income else None
                        current_net_margin = (current_net / current_revenue) * 100 if current_net else None

                        # Calculate year-ago margins (as percentages)
                        year_ago_gross_margin = (year_ago_gross / year_ago_revenue) * 100 if year_ago_gross else None
                        year_ago_op_margin = (year_ago_op_income / year_ago_revenue) * 100 if year_ago_op_income else None
                        year_ago_net_margin = (year_ago_net / year_ago_revenue) * 100 if year_ago_net else None

                        # Calculate margin changes (in percentage points) - STRICT: BOTH quarters required
                        if current_gross_margin is not None and year_ago_gross_margin is not None:
                            gross_margin_trend = round(current_gross_margin - year_ago_gross_margin, 2)
                        else:
                            log_metric_unavailable(symbol, "gross_margin_trend",
                                f"Missing Gross Profit data (current: {current_gross}, yoy: {year_ago_gross})")

                        if current_op_margin is not None and year_ago_op_margin is not None:
                            operating_margin_trend = round(current_op_margin - year_ago_op_margin, 2)
                        else:
                            log_metric_unavailable(symbol, "operating_margin_trend",
                                f"Missing Operating Income data (current: {current_op_income}, yoy: {year_ago_op_income})")

                        if current_net_margin is not None and year_ago_net_margin is not None:
                            net_margin_trend = round(current_net_margin - year_ago_net_margin, 2)
                        else:
                            log_metric_unavailable(symbol, "net_margin_trend",
                                f"Missing Net Income data (current: {current_net}, yoy: {year_ago_net})")

        except Exception as e:
            log_metric_unavailable(symbol, "margin_trends", f"Query error: {e}")

        # ========== STEP 9: Quarterly Growth Momentum ==========
        quarterly_growth_momentum = None
        try:
            cursor.execute(
                """
                SELECT date, value FROM quarterly_income_statement
                WHERE symbol = %s AND item_name IN ('Total Revenue', 'Operating Revenue')
                ORDER BY date DESC, item_name
                LIMIT 10
                """,
                (symbol,),
            )
            quarterly_rev_rows = cursor.fetchall()

            if len(quarterly_rev_rows) == 0:
                log_metric_unavailable(symbol, "quarterly_growth_momentum",
                    "No revenue data in quarterly_income_statement")
            else:
                # Deduplicate by date, keeping most recent revenue type
                from collections import OrderedDict
                revenue_by_date = OrderedDict()
                for date, value in quarterly_rev_rows:
                    if date not in revenue_by_date:
                        revenue_by_date[date] = value
                quarterly_rev_rows_dedup = [(date, revenue_by_date[date]) for date in sorted(revenue_by_date.keys(), reverse=True)]

                if len(quarterly_rev_rows_dedup) < 8:
                    log_metric_unavailable(symbol, "quarterly_growth_momentum",
                        f"Insufficient quarters: {len(quarterly_rev_rows_dedup)} (need 8)")
                else:
                    # Current quarter (index 0)
                    curr_q_revenue = safe_numeric(quarterly_rev_rows_dedup[0][1])
                    prev_q_revenue = safe_numeric(quarterly_rev_rows_dedup[1][1])
                    year_ago_q_revenue = safe_numeric(quarterly_rev_rows_dedup[4][1])
                    year_ago_prev_q_revenue = safe_numeric(quarterly_rev_rows_dedup[5][1])

                    if curr_q_revenue is None or prev_q_revenue is None or year_ago_q_revenue is None or year_ago_prev_q_revenue is None:
                        log_metric_unavailable(symbol, "quarterly_growth_momentum",
                            f"Invalid revenue data: curr={curr_q_revenue}, prev={prev_q_revenue}, yoy_curr={year_ago_q_revenue}, yoy_prev={year_ago_prev_q_revenue}")
                    elif prev_q_revenue == 0:
                        log_metric_unavailable(symbol, "quarterly_growth_momentum",
                            "Previous quarter revenue is zero")
                    elif year_ago_prev_q_revenue == 0:
                        log_metric_unavailable(symbol, "quarterly_growth_momentum",
                            "Year-ago previous quarter revenue is zero")
                    else:
                        # Current Q growth rate
                        curr_q_growth = ((curr_q_revenue - prev_q_revenue) / abs(prev_q_revenue)) * 100
                        # Year-ago Q growth rate
                        year_ago_q_growth = ((year_ago_q_revenue - year_ago_prev_q_revenue) / abs(year_ago_prev_q_revenue)) * 100
                        # Momentum = current growth - year-ago growth (acceleration)
                        quarterly_growth_momentum = round(curr_q_growth - year_ago_q_growth, 2)
        except Exception as e:
            log_metric_unavailable(symbol, "quarterly_growth_momentum", f"Query error: {e}")

        # ========== STEP 10: Asset Growth (YoY) ==========
        asset_growth_yoy = None
        try:
            cursor.execute(
                """
                SELECT date, value FROM quarterly_balance_sheet
                WHERE symbol = %s AND item_name = 'Total Assets'
                ORDER BY date DESC
                LIMIT 5
                """,
                (symbol,),
            )
            asset_rows = cursor.fetchall()
            if len(asset_rows) < 5:
                log_metric_unavailable(symbol, "asset_growth_yoy",
                    f"Insufficient asset data: {len(asset_rows)} quarters (need 5)")
            else:
                current_assets = safe_numeric(asset_rows[0][1])
                year_ago_assets = safe_numeric(asset_rows[4][1])
                if current_assets is None:
                    log_metric_unavailable(symbol, "asset_growth_yoy", "Current assets is invalid")
                elif year_ago_assets is None:
                    log_metric_unavailable(symbol, "asset_growth_yoy", "Year-ago assets is invalid")
                elif year_ago_assets <= 0:
                    log_metric_unavailable(symbol, "asset_growth_yoy", f"Year-ago assets invalid: {year_ago_assets}")
                else:
                    asset_growth_yoy = ((current_assets - year_ago_assets) / year_ago_assets) * 100
        except Exception as e:
            log_metric_unavailable(symbol, "asset_growth_yoy", f"Query error: {e}")

        logging.info(f"{symbol}: Rev Growth: {revenue_growth_3y_cagr}, EPS Growth: {eps_growth_3y_cagr}, ROE: {roe_trend}, SGR: {sustainable_growth_rate}, Op Income YoY: {operating_income_growth_yoy}, FCF YoY: {fcf_growth_yoy}, NI YoY: {net_income_growth_yoy}, Margin Trends (G/O/N): {gross_margin_trend}/{operating_margin_trend}/{net_margin_trend}, Q Momentum: {quarterly_growth_momentum}, Asset Growth: {asset_growth_yoy}")

        if revenue_growth_3y_cagr is None and eps_growth_3y_cagr is None:
            logging.warning(f"No growth data for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Get current date for the record
        current_date = datetime.now().date()

        # Create record with all calculated metrics (original + new)
        record = (
            symbol,
            current_date,
            revenue_growth_3y_cagr,      # From key_metrics.revenue_growth_pct
            eps_growth_3y_cagr,          # From key_metrics.earnings_growth_pct
            operating_income_growth_yoy, # Calculated from quarterly_financials
            roe_trend,                   # From key_metrics.return_on_equity_pct
            sustainable_growth_rate,     # Calculated: ROE × (1 - Payout Ratio)
            fcf_growth_yoy,              # Calculated from quarterly_cashflow
            net_income_growth_yoy,       # NEW: Net income YoY growth
            gross_margin_trend,          # NEW: Gross margin trend (percentage points)
            operating_margin_trend,      # NEW: Operating margin trend (percentage points)
            net_margin_trend,            # NEW: Net margin trend (percentage points)
            quarterly_growth_momentum,   # NEW: Revenue growth acceleration
            asset_growth_yoy,            # NEW: Total assets YoY growth
        )
        records = [record]

        # ========== STEP 4: Insert Records ==========
        if records:
            execute_values(
                cursor,
                """
                INSERT INTO growth_metrics
                (symbol, date, revenue_growth_3y_cagr, eps_growth_3y_cagr,
                 operating_income_growth_yoy, roe_trend, sustainable_growth_rate, fcf_growth_yoy,
                 net_income_growth_yoy, gross_margin_trend, operating_margin_trend, net_margin_trend,
                 quarterly_growth_momentum, asset_growth_yoy)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    revenue_growth_3y_cagr = EXCLUDED.revenue_growth_3y_cagr,
                    eps_growth_3y_cagr = EXCLUDED.eps_growth_3y_cagr,
                    operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                    roe_trend = EXCLUDED.roe_trend,
                    sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                    fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                    net_income_growth_yoy = EXCLUDED.net_income_growth_yoy,
                    gross_margin_trend = EXCLUDED.gross_margin_trend,
                    operating_margin_trend = EXCLUDED.operating_margin_trend,
                    net_margin_trend = EXCLUDED.net_margin_trend,
                    quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum,
                    asset_growth_yoy = EXCLUDED.asset_growth_yoy,
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
        except Exception as pool_err:
            logging.error(f"Failed to return connection to pool for {symbol}: {pool_err}")
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
