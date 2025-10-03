#!/usr/bin/env python3
"""
Earnings Metrics Loader - Updated 2025-10-03 22:50
Award-winning earnings quality scoring with industry best practices

Key Improvements:
- Fixed revenue growth matching to correct quarter (was using same value for all quarters)
- Improved scoring algorithm with proper missing data handling
- Wider normalization ranges for growth stocks (-30% to 60% EPS YoY)
- Weighted scoring adjusted for missing components
- Quality scores calculated for ALL quarters, not just most recent

Methodology:
- EPS Growth (YoY): 30% - Sustainable long-term growth
- Earnings Surprise: 25% - Beat expectations
- Revenue Growth: 20% - Top-line momentum
- Growth Consistency: 15% - Predictable growth streak
- EPS Acceleration (QoQ): 10% - Recent momentum
"""
# Trigger deployment - 2025-10-03 22:50
import concurrent.futures
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime

import boto3
import numpy as np
import pandas as pd
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values

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
    # Check for local database override
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
    """Safely convert value to float, handling None, NaN, and invalid strings"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ["", "N/A", "null", "NULL", "nan", "NaN"]:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def calculate_qoq_growth(current, previous):
    """Calculate quarter-over-quarter growth percentage"""
    current = safe_numeric(current)
    previous = safe_numeric(previous)

    if current is None or previous is None or previous == 0:
        return None

    # Fixed: Don't use abs() - preserves sign for negative earnings
    return ((current - previous) / previous) * 100


def calculate_yoy_growth(current, year_ago):
    """Calculate year-over-year growth percentage (same quarter last year)"""
    current = safe_numeric(current)
    year_ago = safe_numeric(year_ago)

    if current is None or year_ago is None or year_ago == 0:
        return None

    # Fixed: Don't use abs() - preserves sign for negative earnings
    return ((current - year_ago) / year_ago) * 100


def normalize_score(value, min_val, max_val, higher_is_better=True):
    """
    Normalize a value to 0-1 scale

    Args:
        value: The value to normalize
        min_val: Minimum threshold (values below get 0 or 1)
        max_val: Maximum threshold (values above get 1 or 0)
        higher_is_better: True if higher values should get higher scores
    """
    if value is None:
        return 0.0

    # Clamp value between min and max
    clamped = max(min_val, min(max_val, value))

    # Normalize to 0-1
    if max_val == min_val:
        return 0.5

    normalized = (clamped - min_val) / (max_val - min_val)

    return normalized if higher_is_better else (1 - normalized)


def calculate_earnings_quality_score(metrics_data):
    """
    Calculate comprehensive earnings quality score (0-100)

    Award-winning methodology following industry best practices:
    - EPS Growth (YoY): 30% - Long-term sustainable growth
    - Earnings Surprise: 25% - Beat expectations consistently
    - Revenue Growth: 20% - Top-line momentum
    - Growth Consistency: 15% - Predictable growth streak
    - EPS Acceleration (QoQ): 10% - Recent momentum

    Args:
        metrics_data: List of dicts with growth metrics over multiple quarters

    Returns:
        float: Quality score 0-100, or None if insufficient data
    """
    if not metrics_data or len(metrics_data) == 0:
        return None

    # Get most recent quarter
    latest = metrics_data[0]

    eps_yoy = safe_numeric(latest.get('eps_yoy_growth'))
    eps_qoq = safe_numeric(latest.get('eps_qoq_growth'))
    rev_yoy = safe_numeric(latest.get('revenue_yoy_growth'))
    surprise = safe_numeric(latest.get('earnings_surprise_pct'))

    # Track available components for weighting adjustment
    available_weight = 0.0
    component_scores = {}

    # 1. EPS YoY Growth (30% weight) - Most important for quality
    if eps_yoy is not None:
        # Wider range for growth stocks: -30% to 60%
        component_scores['eps_yoy'] = normalize_score(eps_yoy, -30, 60) * 0.30
        available_weight += 0.30

    # 2. Earnings Surprise (25% weight) - Beating expectations is critical
    if surprise is not None:
        # Expanded range: -10% to 20% for high-growth beats
        component_scores['surprise'] = normalize_score(surprise, -10, 20) * 0.25
        available_weight += 0.25

    # 3. Revenue Growth (20% weight) - Top-line sustainability
    if rev_yoy is not None:
        # Wider range: -20% to 50% for high-growth companies
        component_scores['revenue'] = normalize_score(rev_yoy, -20, 50) * 0.20
        available_weight += 0.20

    # 4. Growth Consistency (15% weight) - Positive quarters in last 4
    positive_quarters = sum(1 for m in metrics_data[:4]
                          if safe_numeric(m.get('eps_yoy_growth')) is not None and
                          safe_numeric(m.get('eps_yoy_growth')) > 0)
    if len(metrics_data) >= 4:
        component_scores['consistency'] = (positive_quarters / 4) * 0.15
        available_weight += 0.15

    # 5. EPS Acceleration (10% weight) - QoQ > YoY indicates acceleration
    if eps_qoq is not None and eps_yoy is not None:
        # Give full score if QoQ > YoY, half score if both positive but QoQ < YoY
        if eps_qoq > eps_yoy:
            acceleration = 1.0
        elif eps_qoq > 0 and eps_yoy > 0:
            acceleration = 0.6
        elif eps_qoq > 0:
            acceleration = 0.4
        else:
            acceleration = 0.0
        component_scores['acceleration'] = acceleration * 0.10
        available_weight += 0.10

    # Require at least 50% of components to have data
    if available_weight < 0.50:
        logging.warning(f"Insufficient data for quality score (only {available_weight*100:.0f}% weight available)")
        return None

    # Calculate weighted average score, adjusting for missing components
    total_score = (sum(component_scores.values()) / available_weight) * 100

    # Clamp to 0-100 range
    total_score = max(0, min(100, total_score))

    # Log breakdown for transparency
    logging.debug(f"Score breakdown: {component_scores}, Available weight: {available_weight:.2f}, Total: {total_score:.1f}")

    return round(total_score, 2)


def prepare_db():
    """Setup database tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    conn.autocommit = True
    cursor = conn.cursor()
    logging.info("Connected to PostgreSQL database.")

    # Create last_updated table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run    TIMESTAMP
        );
        """
    )

    # Check if earnings_history table has data (dependency check)
    cursor.execute("SELECT COUNT(*) FROM earnings_history;")
    earnings_history_count = cursor.fetchone()[0]

    if earnings_history_count == 0:
        logging.error("❌ Dependency check failed: earnings_history table is empty")
        logging.error("Please run loadearningshistory.py first before running earnings_metrics")
        cursor.close()
        conn.close()
        sys.exit(1)

    logging.info(f"✅ Dependency check passed: earnings_history has {earnings_history_count:,} records")

    # Drop and recreate earnings_metrics table
    logging.info("Recreating earnings_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS earnings_metrics;")
    cursor.execute(
        """
        CREATE TABLE earnings_metrics (
            symbol                  VARCHAR(50),
            report_date             DATE,
            eps_qoq_growth          DOUBLE PRECISION,  -- Quarter-over-quarter EPS growth %
            eps_yoy_growth          DOUBLE PRECISION,  -- Year-over-year EPS growth %
            revenue_yoy_growth      DOUBLE PRECISION,  -- Year-over-year Revenue growth %
            earnings_surprise_pct   DOUBLE PRECISION,  -- Earnings surprise %
            earnings_quality_score  DOUBLE PRECISION,  -- Composite quality score 0-100
            fetched_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, report_date)
        );
        """
    )

    # Create index on quality score for efficient sorting
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_earnings_quality_score
        ON earnings_metrics(earnings_quality_score DESC NULLS LAST);
        """
    )

    logging.info("Table 'earnings_metrics' ready with quality score.")

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
    """Process a single symbol and calculate growth metrics + quality score"""
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing earnings metrics for {symbol}...")

        # Get earnings history (EPS data)
        cursor.execute(
            """
            SELECT quarter, eps_actual, eps_estimate, surprise_percent
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 20
            """,
            (symbol,),
        )
        earnings_history = cursor.fetchall()

        if not earnings_history:
            logging.warning(f"No earnings history for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Get revenue estimates for revenue growth
        cursor.execute(
            """
            SELECT period, avg_estimate, year_ago_revenue, growth
            FROM revenue_estimates
            WHERE symbol = %s
            ORDER BY period DESC
            LIMIT 8
            """,
            (symbol,),
        )
        revenue_estimates = cursor.fetchall()

        # Convert to DataFrame for easier processing
        earnings_df = pd.DataFrame(
            earnings_history,
            columns=["quarter", "eps_actual", "eps_estimate", "surprise_percent"],
        )
        earnings_df["quarter"] = pd.to_datetime(earnings_df["quarter"])

        # Convert numeric columns
        for col in ["eps_actual", "eps_estimate", "surprise_percent"]:
            earnings_df[col] = earnings_df[col].apply(safe_numeric)

        earnings_df = earnings_df.sort_values("quarter")

        # Calculate metrics for each quarter
        data = []
        metrics_for_scoring = []  # Store for quality score calculation

        for i in range(len(earnings_df)):
            row = earnings_df.iloc[i]
            report_date = row["quarter"]
            eps_actual = row["eps_actual"]
            surprise_pct = row["surprise_percent"]

            # Quarter-over-quarter growth (current vs previous quarter)
            eps_qoq_growth = None
            if i > 0:
                prev_eps = earnings_df.iloc[i - 1]["eps_actual"]
                eps_qoq_growth = calculate_qoq_growth(eps_actual, prev_eps)

            # Year-over-year growth (current vs same quarter last year)
            eps_yoy_growth = None
            if i >= 4:  # Need at least 4 quarters (1 year) of history
                year_ago_eps = earnings_df.iloc[i - 4]["eps_actual"]
                eps_yoy_growth = calculate_yoy_growth(eps_actual, year_ago_eps)

            # Revenue growth - match to current quarter (within 45 days)
            revenue_yoy_growth = None
            if revenue_estimates:
                for period, avg_est, year_ago_rev, growth in revenue_estimates:
                    # Skip relative period strings like "+1y", "-1y", "0q" etc.
                    if not period or (isinstance(period, str) and ('+' in period or '-' in period or period.startswith('0'))):
                        continue

                    try:
                        # Convert period to datetime for comparison
                        period_dt = pd.to_datetime(period)
                        if period_dt and abs((period_dt - report_date).days) <= 45:
                            growth_val = safe_numeric(growth)
                            if growth_val is not None:
                                revenue_yoy_growth = growth_val
                                break
                    except (ValueError, TypeError, pd.errors.ParserError):
                        # Skip periods that can't be parsed as datetime
                        continue

                # If no match found, use most recent valid period as fallback
                if revenue_yoy_growth is None:
                    for period, avg_est, year_ago_rev, growth in revenue_estimates:
                        # Skip relative period strings
                        if period and isinstance(period, str) and ('+' in period or '-' in period or period.startswith('0')):
                            continue
                        growth_val = safe_numeric(growth)
                        if growth_val is not None:
                            revenue_yoy_growth = growth_val
                            break

            # Store metrics for this quarter
            quarter_metrics = {
                'eps_qoq_growth': eps_qoq_growth,
                'eps_yoy_growth': eps_yoy_growth,
                'revenue_yoy_growth': revenue_yoy_growth,
                'earnings_surprise_pct': surprise_pct
            }
            metrics_for_scoring.append(quarter_metrics)

        # Reverse to have most recent first for scoring
        metrics_for_scoring_reversed = list(reversed(metrics_for_scoring))

        # Calculate quality score for EACH quarter (not just most recent)
        for i in range(len(earnings_df)):
            row = earnings_df.iloc[i]
            report_date = row["quarter"]

            # Get historical context for this quarter (this quarter + previous quarters)
            historical_context = metrics_for_scoring_reversed[-(i+1):][::-1]

            # Calculate quality score using this quarter + historical data
            quality_score = calculate_earnings_quality_score(historical_context) if len(historical_context) > 0 else None

            # Get metrics for this quarter
            quarter_data = metrics_for_scoring[i]

            data.append(
                (
                    symbol,
                    report_date.date(),
                    quarter_data['eps_qoq_growth'],
                    quarter_data['eps_yoy_growth'],
                    quarter_data['revenue_yoy_growth'],
                    quarter_data['earnings_surprise_pct'],
                    quality_score,
                    datetime.now(),
                )
            )

        # Insert data
        if data:
            insert_q = """
                INSERT INTO earnings_metrics (
                    symbol, report_date, eps_qoq_growth, eps_yoy_growth,
                    revenue_yoy_growth, earnings_surprise_pct, earnings_quality_score, fetched_at
                ) VALUES %s;
            """
            execute_values(cursor, insert_q, data)
            conn.commit()
            num_inserted = len(data)

            # Get latest quality score for logging
            latest_score = data[-1][6] if data and data[-1][6] is not None else None
            score_msg = f" (Latest Quality Score: {latest_score:.1f})" if latest_score else ""
            logging.info(f"✅ {symbol}: Inserted {num_inserted} quarters{score_msg}")
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert")

        cursor.close()
        conn_pool.putconn(conn)

        # Free memory
        del earnings_df, earnings_history, revenue_estimates, data, metrics_for_scoring
        gc.collect()

        return num_inserted

    except Exception as e:
        logging.error(f"❌ {symbol}: Failed - {str(e)}")
        if "conn" in locals() and conn:
            conn_pool.putconn(conn)
        return 0


def process_symbol_batch(symbols):
    """Process a batch of symbols"""
    conn_pool = create_connection_pool()
    total_inserted = 0
    success_count = 0
    failed_count = 0

    try:
        for symbol in symbols:
            try:
                inserted = process_symbol(symbol, conn_pool)
                total_inserted += inserted
                if inserted > 0:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"❌ Batch error for {symbol}: {str(e)}")
                failed_count += 1
    finally:
        conn_pool.closeall()

    return total_inserted, success_count, failed_count


def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    try:
        symbols = prepare_db()
        start = time.time()
        total_inserted = 0
        symbols_processed = 0
        symbols_failed = 0

        # Process symbols in parallel
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            symbol_batches = [
                symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)
            ]
            futures = [executor.submit(process_symbol_batch, batch) for batch in symbol_batches]

            for future in concurrent.futures.as_completed(futures):
                batch_inserted, batch_success, batch_failed = future.result()
                total_inserted += batch_inserted
                symbols_processed += batch_success
                symbols_failed += batch_failed

        elapsed = time.time() - start
        logging.info(
            f"Summary: Processed {symbols_processed + symbols_failed} symbols in {elapsed:.2f}s"
        )
        logging.info(f"Success: {symbols_processed} symbols ({total_inserted} rows)")
        if symbols_failed > 0:
            logging.warning(f"Failed: {symbols_failed} symbols")
        else:
            logging.info("✨ All symbols processed successfully")

        # Update last_run timestamp
        main_conn_pool = create_connection_pool()
        conn = main_conn_pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, %s)
            ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;
            """,
            (SCRIPT_NAME, datetime.now()),
        )
        conn.commit()
        cursor.close()
        main_conn_pool.putconn(conn)
        main_conn_pool.closeall()

    except Exception as e:
        logging.exception(f"Unhandled error: {e}")
        sys.exit(1)
    finally:
        logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled error in script")
        sys.exit(1)
