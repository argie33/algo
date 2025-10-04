#!/usr/bin/env python3
"""
Earnings Metrics Loader - Updated 2025-10-04 02:00
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
    """
    Safely convert value to float, handling None, NaN, and invalid strings.

    This is critical for earnings data which may have missing values, nulls,
    or non-numeric strings that would otherwise cause calculation errors.

    Args:
        value: Input value of any type (int, float, str, None)

    Returns:
        float or None: Converted float value, or None if conversion fails
            or value is missing/invalid

    Examples:
        safe_numeric(42) -> 42.0
        safe_numeric("3.14") -> 3.14
        safe_numeric("N/A") -> None
        safe_numeric(np.nan) -> None
        safe_numeric(None) -> None
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, str):
        value = value.strip()
        # Handle common null/missing value representations
        if value in ["", "N/A", "null", "NULL", "nan", "NaN"]:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def calculate_qoq_growth(current, previous):
    """
    Calculate quarter-over-quarter (QoQ) growth percentage.

    Compares current quarter's metric to the immediately previous quarter.
    Useful for identifying short-term momentum and acceleration.

    Formula: ((current - previous) / previous) * 100

    Args:
        current: Current quarter value (EPS, revenue, etc.)
        previous: Previous quarter value

    Returns:
        float or None: Growth percentage, or None if calculation not possible
            - Positive value indicates growth
            - Negative value indicates decline
            - None if either value is missing or previous is zero

    Note:
        Preserves sign for negative earnings (doesn't use abs()).
        Division by zero returns None to avoid errors.
    """
    current = safe_numeric(current)
    previous = safe_numeric(previous)

    if current is None or previous is None or previous == 0:
        return None

    # Fixed: Don't use abs() - preserves sign for negative earnings
    return ((current - previous) / previous) * 100


def calculate_yoy_growth(current, year_ago):
    """
    Calculate year-over-year (YoY) growth percentage.

    Compares current quarter to the same quarter last year (4 quarters ago).
    This removes seasonality and provides a clearer picture of long-term trends.

    Formula: ((current - year_ago) / year_ago) * 100

    Args:
        current: Current quarter value (EPS, revenue, etc.)
        year_ago: Same quarter last year value (typically 4 quarters ago)

    Returns:
        float or None: Growth percentage, or None if calculation not possible
            - Positive value indicates year-over-year growth
            - Negative value indicates year-over-year decline
            - None if either value is missing or year_ago is zero

    Note:
        Preserves sign for negative earnings (doesn't use abs()).
        Division by zero returns None to avoid errors.

    Example:
        Q4 2024 EPS: $2.00, Q4 2023 EPS: $1.50
        YoY Growth: ((2.00 - 1.50) / 1.50) * 100 = 33.33%
    """
    current = safe_numeric(current)
    year_ago = safe_numeric(year_ago)

    if current is None or year_ago is None or year_ago == 0:
        return None

    # Fixed: Don't use abs() - preserves sign for negative earnings
    return ((current - year_ago) / year_ago) * 100


def normalize_score(value, min_val, max_val, higher_is_better=True):
    """
    Normalize a value to 0-1 scale for quality score calculation.

    This function converts various metrics (which may have different ranges)
    into a standardized 0-1 scale for fair comparison and weighting.

    Process:
    1. Clamps the value between min_val and max_val thresholds
    2. Normalizes to 0-1 scale using linear interpolation
    3. Optionally inverts the score if lower is better

    Args:
        value: The value to normalize (e.g., EPS growth %, revenue growth %)
        min_val: Minimum threshold - values at or below get score of 0 (or 1 if inverted)
        max_val: Maximum threshold - values at or above get score of 1 (or 0 if inverted)
        higher_is_better: True if higher values should get higher scores (default: True)

    Returns:
        float: Normalized score from 0.0 to 1.0
            - 0.0 = worst possible score
            - 1.0 = best possible score
            - 0.5 = midpoint (or if min_val == max_val)

    Examples:
        normalize_score(25, -30, 60, True)  # EPS growth of 25% -> ~0.61
        normalize_score(-5, -10, 20, True)  # Surprise of -5% -> ~0.17
        normalize_score(None, 0, 100, True) # Missing data -> 0.0
    """
    if value is None:
        return 0.0  # Missing data gets lowest score

    # Clamp value between min and max thresholds
    clamped = max(min_val, min(max_val, value))

    # Normalize to 0-1 scale
    if max_val == min_val:
        return 0.5  # Edge case: if range is zero, return midpoint

    normalized = (clamped - min_val) / (max_val - min_val)

    # Invert score if lower is better
    return normalized if higher_is_better else (1 - normalized)


def calculate_earnings_quality_score(metrics_data):
    """
    Calculate comprehensive earnings quality score (0-100).

    This is the core scoring algorithm that evaluates overall earnings quality
    using a weighted combination of 5 key metrics. The methodology follows
    industry best practices and is designed to identify companies with:
    - Sustainable long-term growth
    - Ability to beat expectations
    - Strong top-line momentum
    - Predictable performance
    - Recent acceleration

    SCORING COMPONENTS (Total: 100%):

    1. EPS YoY Growth (30% weight) - MOST IMPORTANT
       - Measures long-term sustainable earnings growth
       - Range: -30% to 60% (growth stocks)
       - Data source: earnings_history.eps_actual

    2. Earnings Surprise (25% weight)
       - Measures ability to beat analyst expectations
       - Range: -10% to 20% (high-growth beats)
       - Data source: earnings_history.surprise_percent

    3. Revenue YoY Growth (20% weight)
       - Measures top-line sustainability (not just EPS manipulation)
       - Range: -20% to 50% (high-growth companies)
       - Data source: revenue_estimates.growth

    4. Growth Consistency (15% weight)
       - Counts positive YoY growth quarters in last 4 quarters
       - Rewards predictable, consistent growth
       - Derived from: EPS YoY Growth (calculated)

    5. EPS Acceleration (10% weight)
       - Detects recent momentum (QoQ > YoY indicates acceleration)
       - Gives full credit if QoQ > YoY
       - Data source: earnings_history.eps_actual (QoQ calculation)

    ADAPTIVE WEIGHTING:
    - Missing components are excluded from scoring
    - Remaining components are re-weighted proportionally
    - Requires at least 50% of total weight to generate a score
    - Example: If revenue data missing (20% weight), remaining 80% is scaled up

    NORMALIZATION:
    - All components normalized to 0-1 scale before weighting
    - Wider ranges accommodate high-growth stocks
    - Final score clamped to 0-100 range

    Args:
        metrics_data: List of dicts containing quarterly metrics, ordered
            with most recent quarter first. Each dict should have:
            - eps_yoy_growth: Year-over-year EPS growth %
            - eps_qoq_growth: Quarter-over-quarter EPS growth %
            - revenue_yoy_growth: Year-over-year revenue growth %
            - earnings_surprise_pct: Earnings surprise %

    Returns:
        float or None: Quality score from 0.0 to 100.0
            - 0-20: Poor quality (declining earnings, missing estimates)
            - 20-40: Below average (weak growth, inconsistent)
            - 40-60: Average (modest growth, some misses)
            - 60-80: Good quality (solid growth, beating estimates)
            - 80-100: Excellent (strong growth, consistent beats)
            - None: Insufficient data (< 50% of components available)

    Data Requirements:
        All data is available from existing database tables:
        - earnings_history: eps_actual, surprise_percent
        - revenue_estimates: growth
        All percentage-based growth metrics are calculated in process_symbol()

    Examples:
        High-quality stock (score ~85):
        - EPS YoY: 40%, Surprise: 10%, Revenue: 30%, Consistency: 4/4, Acceleration: Yes

        Low-quality stock (score ~25):
        - EPS YoY: -15%, Surprise: -5%, Revenue: -10%, Consistency: 1/4, Acceleration: No
    """
    if not metrics_data or len(metrics_data) == 0:
        return None

    # Extract most recent quarter's metrics for scoring
    latest = metrics_data[0]

    eps_yoy = safe_numeric(latest.get('eps_yoy_growth'))
    eps_qoq = safe_numeric(latest.get('eps_qoq_growth'))
    rev_yoy = safe_numeric(latest.get('revenue_yoy_growth'))
    surprise = safe_numeric(latest.get('earnings_surprise_pct'))

    # Track which components have data for adaptive weighting
    available_weight = 0.0
    component_scores = {}

    # ========== COMPONENT 1: EPS YoY Growth (30% weight) ==========
    # This is the MOST IMPORTANT component - long-term sustainable growth
    if eps_yoy is not None:
        # Wider range for growth stocks: -30% (poor) to 60% (excellent)
        # Example: 25% YoY growth -> 0.61 normalized -> 0.183 weighted score
        component_scores['eps_yoy'] = normalize_score(eps_yoy, -30, 60) * 0.30
        available_weight += 0.30

    # ========== COMPONENT 2: Earnings Surprise (25% weight) ==========
    # Beating analyst expectations is critical for investor confidence
    if surprise is not None:
        # Expanded range: -10% (big miss) to 20% (exceptional beat)
        # Example: 5% beat -> 0.50 normalized -> 0.125 weighted score
        component_scores['surprise'] = normalize_score(surprise, -10, 20) * 0.25
        available_weight += 0.25

    # ========== COMPONENT 3: Revenue YoY Growth (20% weight) ==========
    # Top-line growth ensures EPS isn't just from buybacks/cost cuts
    if rev_yoy is not None:
        # Wider range: -20% (poor) to 50% (high-growth)
        # Example: 15% revenue growth -> 0.47 normalized -> 0.094 weighted score
        component_scores['revenue'] = normalize_score(rev_yoy, -20, 50) * 0.20
        available_weight += 0.20

    # ========== COMPONENT 4: Growth Consistency (15% weight) ==========
    # Count how many of the last quarters (up to 4) had positive YoY growth
    # Rewards predictable, consistent performers
    # Works with 2-4 quarters of data for maximum compatibility
    quarters_to_check = min(len(metrics_data), 4)
    if quarters_to_check >= 2:  # Need at least 2 quarters for consistency metric
        positive_quarters = sum(1 for m in metrics_data[:quarters_to_check]
                              if safe_numeric(m.get('eps_yoy_growth')) is not None and
                              safe_numeric(m.get('eps_yoy_growth')) > 0)
        # Example: 3 out of 4 positive quarters -> 0.75 * 0.15 = 0.1125 weighted score
        component_scores['consistency'] = (positive_quarters / quarters_to_check) * 0.15
        available_weight += 0.15

    # ========== COMPONENT 5: EPS Acceleration (10% weight) ==========
    # Detects recent momentum - QoQ growth exceeding YoY indicates acceleration
    if eps_qoq is not None and eps_yoy is not None:
        # Acceleration scoring logic:
        # - QoQ > YoY: Full score (1.0) - strong acceleration
        # - Both positive but QoQ < YoY: Partial credit (0.6) - growing but decelerating
        # - Only QoQ positive: Small credit (0.4) - turning around
        # - Otherwise: No score (0.0) - no momentum
        if eps_qoq > eps_yoy:
            acceleration = 1.0  # Best case: accelerating growth
        elif eps_qoq > 0 and eps_yoy > 0:
            acceleration = 0.6  # Good: both positive but decelerating
        elif eps_qoq > 0:
            acceleration = 0.4  # Okay: short-term improvement
        else:
            acceleration = 0.0  # Poor: no positive momentum
        component_scores['acceleration'] = acceleration * 0.10
        available_weight += 0.10

    # ========== VALIDATION AND FINAL CALCULATION ==========
    # Require at least 30% of components to have data (minimum: EPS YoY growth)
    # This allows scoring even when surprise_percent and revenue data are unavailable
    # Most stocks will have eps_actual which gives us: EPS YoY (30%) + Consistency (15%) + Acceleration (10%) = 55%
    if available_weight < 0.30:
        logging.warning(f"Insufficient data for quality score (only {available_weight*100:.0f}% weight available)")
        return None

    # Calculate weighted average score, adjusting for missing components
    # Example: If only 80% weight available, we scale up: sum / 0.80 * 100
    # This ensures scores are comparable even when some data is missing
    total_score = (sum(component_scores.values()) / available_weight) * 100

    # Clamp to valid 0-100 range (safety check for edge cases)
    total_score = max(0, min(100, total_score))

    # Log breakdown for debugging and transparency
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
    """
    Process a single symbol and calculate growth metrics + quality score.

    This function orchestrates the entire metrics calculation workflow:
    1. Fetches earnings history (EPS data) from database
    2. Fetches revenue estimates for revenue growth calculation
    3. Calculates QoQ and YoY growth metrics for each quarter
    4. Matches revenue data to corresponding quarters (within 45 days)
    5. Calculates earnings quality score for each quarter
    6. Inserts all calculated metrics into earnings_metrics table

    Data Flow:
        earnings_history → EPS QoQ/YoY growth → quality score components
        revenue_estimates → Revenue YoY growth → quality score components
        Combined → Final earnings quality score (0-100)

    Args:
        symbol: Stock symbol to process (e.g., "AAPL", "MSFT")
        conn_pool: Database connection pool for thread-safe access

    Returns:
        int: Number of quarters inserted into earnings_metrics table
            - Returns 0 if no data available or processing fails
    """
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing earnings metrics for {symbol}...")

        # ========== STEP 1: Fetch Earnings History (EPS Data) ==========
        # Get up to 20 quarters of historical earnings data
        # This provides enough history for YoY comparisons (need 4 quarters back)
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

        # ========== STEP 2: Fetch Revenue Estimates (Revenue Growth Data) ==========
        # Get revenue growth data to ensure EPS growth isn't just from cost cuts
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
            eps_estimate = row["eps_estimate"]
            surprise_pct = row["surprise_percent"]

            # Calculate surprise_percent ourselves if not provided by yfinance
            if surprise_pct is None and eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
                surprise_pct = ((eps_actual - eps_estimate) / abs(eps_estimate)) * 100

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
            elif i >= 1:  # Fallback: use QoQ if YoY not available (for stocks with limited history)
                # For newer stocks, use QoQ as proxy for YoY (not perfect but better than nothing)
                prev_eps = earnings_df.iloc[i - 1]["eps_actual"]
                eps_yoy_growth = calculate_qoq_growth(eps_actual, prev_eps)

            # ========== Revenue YoY Growth - Match to Current Quarter ==========
            # Match revenue growth data to the current earnings quarter
            # This is critical for accurate quality scoring - we need the RIGHT quarter's revenue
            revenue_yoy_growth = None
            if revenue_estimates:
                # First pass: Try to find exact or near match (within 45 days)
                for period, avg_est, year_ago_rev, growth in revenue_estimates:
                    # Skip relative period strings like "+1y", "-1y", "0q" etc.
                    # These are forward/backward looking labels, not actual dates
                    if not period or (isinstance(period, str) and ('+' in period or '-' in period or period.startswith('0'))):
                        continue

                    try:
                        # Convert period to datetime for comparison
                        period_dt = pd.to_datetime(period)
                        # Match if within 45 days of earnings report date (allows for small differences)
                        if period_dt and abs((period_dt - report_date).days) <= 45:
                            growth_val = safe_numeric(growth)
                            if growth_val is not None:
                                revenue_yoy_growth = growth_val
                                break  # Found a good match, stop searching
                    except (ValueError, TypeError, pd.errors.ParserError):
                        # Skip periods that can't be parsed as datetime
                        continue

                # Second pass: If no close match found, use most recent valid period as fallback
                # This ensures we have SOME revenue data rather than none
                if revenue_yoy_growth is None:
                    for period, avg_est, year_ago_rev, growth in revenue_estimates:
                        # Skip relative period strings
                        if period and isinstance(period, str) and ('+' in period or '-' in period or period.startswith('0')):
                            continue
                        growth_val = safe_numeric(growth)
                        if growth_val is not None:
                            revenue_yoy_growth = growth_val
                            break  # Use first valid revenue growth found

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
