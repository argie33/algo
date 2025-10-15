#!/usr/bin/env python3
"""
Relative Strength Loader - Professional RS Factor Score
Calculates comprehensive relative strength metrics for all stocks

Components:
1. Cross-Sectional RS (vs all stocks) - IBD-style percentile ranking
2. Sector-Relative RS (vs sector peers) - Sector leadership identification
3. RS Momentum (acceleration) - Is RS improving or deteriorating?
4. RS Consistency (reliability) - How stable is the outperformance?
5. Multi-Timeframe Alignment - Are all timeframes confirming?

Based on: IBD RS Rating, O'Neil methodology, AQR research
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

# Register numpy type adapters
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

    # Create last_updated table
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

    # Drop and recreate relative_strength_metrics table
    logging.info("Creating relative_strength_metrics table...")
    cursor.execute("DROP TABLE IF EXISTS relative_strength_metrics;")
    cursor.execute(
        """
        CREATE TABLE relative_strength_metrics (
            symbol                      VARCHAR(50),
            date                        DATE,

            -- Cross-Sectional RS (vs all stocks)
            rs_rating                   INTEGER,           -- IBD-style 0-99 percentile
            rs_rating_score             DOUBLE PRECISION,  -- Contribution to total score (0-40)

            -- Sector-Relative RS (vs sector peers)
            sector_relative_1m          DOUBLE PRECISION,  -- 1-month outperformance vs sector
            sector_relative_3m          DOUBLE PRECISION,  -- 3-month outperformance vs sector
            sector_relative_6m          DOUBLE PRECISION,  -- 6-month outperformance vs sector
            sector_relative_12m         DOUBLE PRECISION,  -- 12-month outperformance vs sector
            sector_percentile           DOUBLE PRECISION,  -- Percentile rank within sector (0-100)
            sector_rs_score             DOUBLE PRECISION,  -- Contribution to total score (0-25)

            -- RS Momentum (acceleration)
            mansfield_rs_current        DOUBLE PRECISION,  -- Current Mansfield RS
            mansfield_rs_4w_ago         DOUBLE PRECISION,  -- Mansfield RS 4 weeks ago
            mansfield_rs_13w_ago        DOUBLE PRECISION,  -- Mansfield RS 13 weeks ago
            rs_momentum_4w              DOUBLE PRECISION,  -- 4-week RS change
            rs_momentum_13w             DOUBLE PRECISION,  -- 13-week RS change
            rs_momentum_score           DOUBLE PRECISION,  -- Contribution to total score (0-20)

            -- RS Consistency (reliability)
            positive_months_12          INTEGER,           -- Positive months out of 12
            rs_consistency_pct          DOUBLE PRECISION,  -- % of positive months
            rs_std_dev                  DOUBLE PRECISION,  -- Standard deviation of monthly RS
            rs_consistency_score        DOUBLE PRECISION,  -- Contribution to total score (0-10)

            -- Multi-Timeframe Alignment
            roc_1m                      DOUBLE PRECISION,  -- 1-month return
            roc_3m                      DOUBLE PRECISION,  -- 3-month return
            roc_6m                      DOUBLE PRECISION,  -- 6-month return
            roc_12m                     DOUBLE PRECISION,  -- 12-month return
            timeframe_alignment         INTEGER,           -- Count of positive timeframes (0-4)
            alignment_score             DOUBLE PRECISION,  -- Contribution to total score (0-5)

            -- Total Relative Strength Score
            relative_strength_score     DOUBLE PRECISION,  -- Final composite score (0-100)

            -- Metadata
            sector                      VARCHAR(100),
            fetched_at                  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """
    )

    # Create indexes
    logging.info("Creating indexes on relative_strength_metrics...")
    cursor.execute("CREATE INDEX idx_rs_metrics_symbol ON relative_strength_metrics(symbol);")
    cursor.execute("CREATE INDEX idx_rs_metrics_date ON relative_strength_metrics(date DESC);")
    cursor.execute("CREATE INDEX idx_rs_metrics_score ON relative_strength_metrics(relative_strength_score DESC);")
    cursor.execute("CREATE INDEX idx_rs_metrics_sector ON relative_strength_metrics(sector);")
    conn.commit()
    logging.info("Indexes created successfully")

    logging.info("Table 'relative_strength_metrics' ready.")

    # Get stock symbols with their sectors
    cursor.execute("""
        SELECT DISTINCT s.symbol, COALESCE(cp.sector, 'Unknown') as sector
        FROM stock_symbols s
        LEFT JOIN company_profile cp ON s.symbol = cp.ticker
        WHERE (s.etf IS NULL OR s.etf != 'Y')
        AND s.symbol IS NOT NULL
    """)
    symbols_sectors = cursor.fetchall()
    logging.info(f"Found {len(symbols_sectors)} symbols.")

    cursor.close()
    conn.close()
    return symbols_sectors


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


def calculate_rs_rating(symbol, stock_rocs, all_stock_rocs):
    """
    Calculate IBD-style RS Rating (0-99 percentile)
    Weighted multi-timeframe approach:
    - 40% weight on 12-month
    - 20% weight on 9-month
    - 20% weight on 6-month
    - 20% weight on 3-month
    """
    # Calculate weighted composite score for this stock
    composite = (
        0.40 * stock_rocs.get('roc_252d', 0) +
        0.20 * stock_rocs.get('roc_189d', 0) +
        0.20 * stock_rocs.get('roc_120d', 0) +
        0.20 * stock_rocs.get('roc_60d', 0)
    )

    # Calculate percentile rank
    if not all_stock_rocs:
        return 50, 20  # Default middle score

    scores = [
        0.40 * s.get('roc_252d', 0) +
        0.20 * s.get('roc_189d', 0) +
        0.20 * s.get('roc_120d', 0) +
        0.20 * s.get('roc_60d', 0)
        for s in all_stock_rocs
    ]

    percentile = (sum(1 for s in scores if s < composite) / len(scores)) * 100
    rs_rating = min(99, max(0, int(percentile)))

    # Convert to score contribution (0-40 points)
    rs_rating_score = (rs_rating / 99) * 40

    return rs_rating, rs_rating_score


def process_symbol(symbol_sector, conn_pool, all_stock_data, sector_data):
    """
    Process a single symbol and calculate all RS metrics

    Args:
        symbol_sector: Tuple of (symbol, sector)
        conn_pool: Database connection pool
        all_stock_data: Dict of all stock ROC data for percentile calculations
        sector_data: Dict of sector performance data

    Returns:
        int: 1 if successful, 0 otherwise
    """
    symbol, sector = symbol_sector

    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing RS metrics for {symbol} ({sector})...")
        current_date = datetime.now().date()

        # ========== STEP 1: Fetch Multi-Timeframe Data ==========
        # Get current technical data
        cursor.execute(
            """
            SELECT
                roc_20d, roc_60d, roc_120d, roc_189d, roc_252d,
                mansfield_rs, date
            FROM technical_data_daily
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol,),
        )
        current_tech = cursor.fetchone()

        if not current_tech:
            logging.warning(f"No technical data for {symbol}")
            conn_pool.putconn(conn)
            return 0

        roc_1m, roc_3m, roc_6m, roc_9m, roc_12m, mansfield_current, tech_date = current_tech

        # Get historical Mansfield RS for momentum calculation
        cursor.execute(
            """
            SELECT mansfield_rs, date
            FROM technical_data_daily
            WHERE symbol = %s
            AND date <= %s - INTERVAL '4 weeks'
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol, tech_date),
        )
        mansfield_4w = cursor.fetchone()
        mansfield_4w_ago = mansfield_4w[0] if mansfield_4w else mansfield_current

        cursor.execute(
            """
            SELECT mansfield_rs, date
            FROM technical_data_daily
            WHERE symbol = %s
            AND date <= %s - INTERVAL '13 weeks'
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol, tech_date),
        )
        mansfield_13w = cursor.fetchone()
        mansfield_13w_ago = mansfield_13w[0] if mansfield_13w else mansfield_current

        # ========== STEP 2: Calculate Cross-Sectional RS ==========
        stock_rocs = {
            'roc_60d': safe_numeric(roc_3m) or 0,
            'roc_120d': safe_numeric(roc_6m) or 0,
            'roc_189d': safe_numeric(roc_9m) or 0,
            'roc_252d': safe_numeric(roc_12m) or 0,
        }

        rs_rating, rs_rating_score = calculate_rs_rating(symbol, stock_rocs, all_stock_data)
        logging.info(f"{symbol}: RS Rating = {rs_rating} ({rs_rating_score:.1f} points)")

        # ========== STEP 3: Calculate Sector-Relative RS ==========
        sector_perf = sector_data.get(sector, {})

        # Calculate outperformance vs sector
        sector_relative_1m = (safe_numeric(roc_1m) or 0) - sector_perf.get('performance_1m', 0)
        sector_relative_3m = (safe_numeric(roc_3m) or 0) - sector_perf.get('performance_3m', 0)
        sector_relative_6m = (safe_numeric(roc_6m) or 0) - sector_perf.get('performance_6m', 0)
        sector_relative_12m = (safe_numeric(roc_12m) or 0) - sector_perf.get('performance_12m', 0)

        # Weighted sector relative score
        sector_relative_composite = (
            0.20 * sector_relative_1m +
            0.20 * sector_relative_3m +
            0.30 * sector_relative_6m +
            0.30 * sector_relative_12m
        )

        # Calculate sector percentile
        sector_stocks = sector_perf.get('stocks_performance', [])
        if sector_stocks:
            sector_percentile = (sum(1 for s in sector_stocks if s < sector_relative_composite) / len(sector_stocks)) * 100
        else:
            sector_percentile = 50

        # Normalize to score (0-25 points)
        # >15% outperformance = 25 points, -15% underperformance = 0 points
        sector_rs_score = min(25, max(0, ((sector_relative_composite + 15) / 30) * 25))
        logging.info(f"{symbol}: Sector RS = {sector_relative_composite:.2f}% ({sector_rs_score:.1f} points)")

        # ========== STEP 4: Calculate RS Momentum ==========
        rs_momentum_4w = (safe_numeric(mansfield_current) or 0) - (safe_numeric(mansfield_4w_ago) or 0)
        rs_momentum_13w = (safe_numeric(mansfield_current) or 0) - (safe_numeric(mansfield_13w_ago) or 0)

        # Score RS momentum (0-20 points)
        if rs_momentum_4w > 5 and rs_momentum_13w > 10:
            rs_momentum_score = 20  # Strong acceleration
        elif rs_momentum_4w > 0 and rs_momentum_13w > 0:
            rs_momentum_score = 15  # Improving
        elif rs_momentum_4w > 0 or rs_momentum_13w > 0:
            rs_momentum_score = 10  # Mixed
        elif rs_momentum_4w < -5 and rs_momentum_13w < -10:
            rs_momentum_score = 0   # Deteriorating
        else:
            rs_momentum_score = 5   # Neutral/weak

        logging.info(f"{symbol}: RS Momentum = 4w:{rs_momentum_4w:.2f}, 13w:{rs_momentum_13w:.2f} ({rs_momentum_score:.1f} points)")

        # ========== STEP 5: Calculate RS Consistency ==========
        # Get monthly returns for last 12 months
        cursor.execute(
            """
            SELECT
                EXTRACT(MONTH FROM date) as month,
                EXTRACT(YEAR FROM date) as year,
                AVG(close) as avg_close
            FROM price_daily
            WHERE symbol = %s
            AND date >= %s - INTERVAL '12 months'
            GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
            ORDER BY year DESC, month DESC
            LIMIT 12
            """,
            (symbol, tech_date),
        )
        monthly_prices = cursor.fetchall()

        positive_months_12 = 0
        monthly_returns = []

        if len(monthly_prices) >= 2:
            for i in range(len(monthly_prices) - 1):
                current_month = monthly_prices[i][2]
                prev_month = monthly_prices[i + 1][2]
                if current_month and prev_month and prev_month > 0:
                    monthly_return = ((current_month - prev_month) / prev_month) * 100
                    monthly_returns.append(monthly_return)
                    if monthly_return > 0:
                        positive_months_12 += 1

        rs_consistency_pct = (positive_months_12 / 12 * 100) if monthly_returns else 50
        rs_std_dev = np.std(monthly_returns) if len(monthly_returns) > 1 else 0

        # Score consistency (0-10 points)
        rs_consistency_score = (positive_months_12 / 12) * 10
        logging.info(f"{symbol}: RS Consistency = {positive_months_12}/12 positive months ({rs_consistency_score:.1f} points)")

        # ========== STEP 6: Calculate Multi-Timeframe Alignment ==========
        timeframes = [
            safe_numeric(roc_1m) or 0,
            safe_numeric(roc_3m) or 0,
            safe_numeric(roc_6m) or 0,
            safe_numeric(roc_12m) or 0,
        ]

        timeframe_alignment = sum(1 for tf in timeframes if tf > 0)

        # Score alignment (0-5 points)
        if timeframe_alignment == 4:
            alignment_score = 5  # All bullish
        elif timeframe_alignment == 3:
            alignment_score = 3  # Mostly bullish
        elif timeframe_alignment == 2:
            alignment_score = 2  # Mixed
        else:
            alignment_score = 0  # Bearish

        logging.info(f"{symbol}: Timeframe Alignment = {timeframe_alignment}/4 ({alignment_score:.1f} points)")

        # ========== STEP 7: Calculate Total RS Score ==========
        relative_strength_score = (
            rs_rating_score +
            sector_rs_score +
            rs_momentum_score +
            rs_consistency_score +
            alignment_score
        )

        logging.info(f"✅ {symbol}: Total RS Score = {relative_strength_score:.1f}/100")

        # ========== STEP 8: Insert Record ==========
        record = (
            symbol,
            current_date,
            # Cross-sectional
            rs_rating,
            rs_rating_score,
            # Sector-relative
            sector_relative_1m,
            sector_relative_3m,
            sector_relative_6m,
            sector_relative_12m,
            sector_percentile,
            sector_rs_score,
            # RS momentum
            safe_numeric(mansfield_current),
            safe_numeric(mansfield_4w_ago),
            safe_numeric(mansfield_13w_ago),
            rs_momentum_4w,
            rs_momentum_13w,
            rs_momentum_score,
            # RS consistency
            positive_months_12,
            rs_consistency_pct,
            rs_std_dev,
            rs_consistency_score,
            # Timeframe alignment
            safe_numeric(roc_1m),
            safe_numeric(roc_3m),
            safe_numeric(roc_6m),
            safe_numeric(roc_12m),
            timeframe_alignment,
            alignment_score,
            # Total score
            relative_strength_score,
            # Metadata
            sector,
        )

        execute_values(
            cursor,
            """
            INSERT INTO relative_strength_metrics
            (symbol, date,
             rs_rating, rs_rating_score,
             sector_relative_1m, sector_relative_3m, sector_relative_6m, sector_relative_12m,
             sector_percentile, sector_rs_score,
             mansfield_rs_current, mansfield_rs_4w_ago, mansfield_rs_13w_ago,
             rs_momentum_4w, rs_momentum_13w, rs_momentum_score,
             positive_months_12, rs_consistency_pct, rs_std_dev, rs_consistency_score,
             roc_1m, roc_3m, roc_6m, roc_12m, timeframe_alignment, alignment_score,
             relative_strength_score, sector)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                rs_rating = EXCLUDED.rs_rating,
                rs_rating_score = EXCLUDED.rs_rating_score,
                sector_relative_1m = EXCLUDED.sector_relative_1m,
                sector_relative_3m = EXCLUDED.sector_relative_3m,
                sector_relative_6m = EXCLUDED.sector_relative_6m,
                sector_relative_12m = EXCLUDED.sector_relative_12m,
                sector_percentile = EXCLUDED.sector_percentile,
                sector_rs_score = EXCLUDED.sector_rs_score,
                mansfield_rs_current = EXCLUDED.mansfield_rs_current,
                mansfield_rs_4w_ago = EXCLUDED.mansfield_rs_4w_ago,
                mansfield_rs_13w_ago = EXCLUDED.mansfield_rs_13w_ago,
                rs_momentum_4w = EXCLUDED.rs_momentum_4w,
                rs_momentum_13w = EXCLUDED.rs_momentum_13w,
                rs_momentum_score = EXCLUDED.rs_momentum_score,
                positive_months_12 = EXCLUDED.positive_months_12,
                rs_consistency_pct = EXCLUDED.rs_consistency_pct,
                rs_std_dev = EXCLUDED.rs_std_dev,
                rs_consistency_score = EXCLUDED.rs_consistency_score,
                roc_1m = EXCLUDED.roc_1m,
                roc_3m = EXCLUDED.roc_3m,
                roc_6m = EXCLUDED.roc_6m,
                roc_12m = EXCLUDED.roc_12m,
                timeframe_alignment = EXCLUDED.timeframe_alignment,
                alignment_score = EXCLUDED.alignment_score,
                relative_strength_score = EXCLUDED.relative_strength_score,
                sector = EXCLUDED.sector,
                fetched_at = CURRENT_TIMESTAMP
            """,
            [record],
        )
        conn.commit()

        conn_pool.putconn(conn)
        return 1

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        try:
            conn_pool.putconn(conn)
        except:
            pass
        return 0


def load_all_stock_data(conn_pool):
    """Load all stock ROC data for percentile calculations"""
    conn = conn_pool.getconn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT symbol, roc_60d, roc_120d, roc_189d, roc_252d
        FROM technical_data_daily
        WHERE date = (SELECT MAX(date) FROM technical_data_daily)
        AND roc_252d IS NOT NULL
    """)

    all_data = []
    for row in cursor.fetchall():
        all_data.append({
            'symbol': row[0],
            'roc_60d': safe_numeric(row[1]) or 0,
            'roc_120d': safe_numeric(row[2]) or 0,
            'roc_189d': safe_numeric(row[3]) or 0,
            'roc_252d': safe_numeric(row[4]) or 0,
        })

    cursor.close()
    conn_pool.putconn(conn)

    logging.info(f"Loaded ROC data for {len(all_data)} stocks")
    return all_data


def load_sector_data(conn_pool):
    """Load sector performance data"""
    conn = conn_pool.getconn()
    cursor = conn.cursor()

    # For now, return empty dict - this should be populated with actual sector averages
    # TODO: Calculate sector averages from stock data or use sector_performance table

    cursor.close()
    conn_pool.putconn(conn)

    return {}


def main():
    """Main execution function"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Relative Strength Metrics Loader - Starting")
    logging.info("Components: Cross-Sectional, Sector-Relative, RS Momentum, Consistency, Alignment")
    logging.info("=" * 80)

    # Initialize database and get symbols
    symbols_sectors = initialize_db()

    # Create connection pool
    conn_pool = create_connection_pool()

    # Load reference data
    logging.info("Loading reference data...")
    all_stock_data = load_all_stock_data(conn_pool)
    sector_data = load_sector_data(conn_pool)

    # Process symbols in parallel
    total_records = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_symbol, sym_sec, conn_pool, all_stock_data, sector_data): sym_sec[0]
            for sym_sec in symbols_sectors
        }

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
    logging.info(f"✅ Relative Strength Metrics Loader Complete!")
    logging.info(f"   Total Records: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols_sectors)}")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
