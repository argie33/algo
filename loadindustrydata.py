#!/usr/bin/env python3
"""
Industry Performance Loader
Calculates IBD-style industry group rankings with trend analysis
Aggregates stock performance by industry within sectors

Trigger rebuild: 20251016_143500 - Populate industry performance data to AWS
"""

import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from statistics import median

import boto3
import numpy as np
import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

SCRIPT_NAME = "loadindustrydata.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_db_config():
    """Fetch database credentials from AWS Secrets Manager or use local environment"""
    if os.getenv("USE_LOCAL_DB") == "true" or all(
        key in os.environ for key in ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    ):
        logging.info("Using local database configuration from environment variables")
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", 5432)),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
            "dbname": os.getenv("DB_NAME", "stocks"),
        }

    # AWS Secrets Manager for production
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"],
    }


def calculate_rs_rating(industry_perf, all_perf):
    """
    Calculate IBD-style RS Rating (1-99)
    Compares industry performance to all other industries
    """
    if not all_perf or len(all_perf) < 2:
        return 50  # Default to middle

    # Sort all performances
    sorted_perf = sorted(all_perf)

    # Find percentile rank
    rank = sorted_perf.index(industry_perf) if industry_perf in sorted_perf else 0
    for i, perf in enumerate(sorted_perf):
        if industry_perf <= perf:
            rank = i
            break

    # Convert to 1-99 scale
    percentile = (rank / len(sorted_perf)) * 100
    rs_rating = min(99, max(1, int(percentile)))

    return rs_rating


def determine_momentum(perf_1d, perf_5d, perf_20d):
    """Determine momentum based on multi-period performance"""
    # Strong: All positive with acceleration
    if perf_1d > 0 and perf_5d > 0 and perf_20d > 0:
        if perf_1d > perf_5d / 5 and perf_5d > perf_20d / 4:
            return "Strong"

    # Weak: All negative with deceleration
    if perf_1d < 0 and perf_5d < 0 and perf_20d < 0:
        if perf_1d < perf_5d / 5 and perf_5d < perf_20d / 4:
            return "Weak"

    return "Moderate"


def determine_trend(perf_5d, perf_20d):
    """Determine trend direction"""
    if perf_5d > 1 and perf_20d > 2:
        return "Uptrend"
    elif perf_5d < -1 and perf_20d < -2:
        return "Downtrend"
    else:
        return "Sideways"


def fetch_stock_performance(symbol, period="3mo"):
    """Fetch individual stock performance metrics"""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)

        if hist.empty or len(hist) < 5:
            return None

        # Calculate performance metrics
        current = hist['Close'].iloc[-1]
        prices = hist['Close'].values

        perf_1d = ((current - prices[-2]) / prices[-2] * 100) if len(prices) >= 2 else 0
        perf_5d = ((current - prices[-6]) / prices[-6] * 100) if len(prices) >= 6 else 0
        perf_20d = ((current - prices[-21]) / prices[-21] * 100) if len(prices) >= 21 else 0

        # Get market cap from info
        info = ticker.info
        market_cap = info.get('marketCap', 0)

        return {
            'symbol': symbol,
            'current_price': float(current),
            'change': float(current - prices[-2]) if len(prices) >= 2 else 0,
            'change_percent': float(perf_1d),
            'volume': int(hist['Volume'].iloc[-1]),
            'market_cap': market_cap,
            'perf_1d': float(perf_1d),
            'perf_5d': float(perf_5d),
            'perf_20d': float(perf_20d),
        }

    except Exception as e:
        logging.debug(f"Failed to fetch {symbol}: {e}")
        return None


def get_industry_stocks(cur):
    """Get all stocks grouped by sector and industry"""
    cur.execute("""
        SELECT
            COALESCE(sector, 'Unknown') as sector,
            COALESCE(industry, 'Unknown') as industry,
            industry_key,
            ticker
        FROM company_profile
        WHERE sector IS NOT NULL
        AND industry IS NOT NULL
        AND ticker IS NOT NULL
        ORDER BY sector, industry, ticker
    """)

    rows = cur.fetchall()

    # Group by sector -> industry
    industries = {}
    for sector, industry, industry_key, ticker in rows:
        key = (sector, industry)
        if key not in industries:
            industries[key] = {
                'sector': sector,
                'industry': industry,
                'industry_key': industry_key,
                'symbols': []
            }
        industries[key]['symbols'].append(ticker)

    return industries


def calculate_industry_performance(cur, spy_prices=None):
    """Calculate performance metrics for each industry"""
    logging.info("Fetching industry stock groups...")
    industries = get_industry_stocks(cur)
    logging.info(f"Found {len(industries)} industries to analyze")

    industry_data = []
    all_performances = []  # For RS rating calculation

    for (sector, industry), info in industries.items():
        symbols = info['symbols']

        # Skip industries with too few stocks
        if len(symbols) < 2:
            logging.debug(f"Skipping {industry} ({sector}) - only {len(symbols)} stock(s)")
            continue

        logging.info(f"Analyzing {industry} ({sector}) - {len(symbols)} stocks")

        # Fetch performance for all stocks in industry
        stock_performances = []
        total_market_cap = 0
        total_volume = 0

        for symbol in symbols[:50]:  # Limit to top 50 stocks per industry
            perf = fetch_stock_performance(symbol)
            if perf:
                stock_performances.append(perf)
                total_market_cap += perf['market_cap']
                total_volume += perf['volume']

            time.sleep(0.1)  # Rate limiting

        # Skip if not enough data
        if len(stock_performances) < 2:
            logging.warning(f"Not enough data for {industry} - got {len(stock_performances)}/{len(symbols)}")
            continue

        # Calculate aggregate metrics
        change_percents = [s['change_percent'] for s in stock_performances]
        perf_1ds = [s['perf_1d'] for s in stock_performances]
        perf_5ds = [s['perf_5d'] for s in stock_performances]
        perf_20ds = [s['perf_20d'] for s in stock_performances]
        market_caps = [s['market_cap'] for s in stock_performances if s['market_cap'] > 0]

        avg_change_percent = np.mean(change_percents)
        median_change_percent = median(change_percents)
        avg_perf_1d = np.mean(perf_1ds)
        avg_perf_5d = np.mean(perf_5ds)
        avg_perf_20d = np.mean(perf_20ds)

        # Calculate RS vs SPY
        rs_vs_spy = 0
        if spy_prices is not None and len(spy_prices) >= 20:
            spy_perf = ((spy_prices[-1] - spy_prices[-20]) / spy_prices[-20]) * 100
            rs_vs_spy = avg_perf_20d - spy_perf

        # Determine momentum and trend
        momentum = determine_momentum(avg_perf_1d, avg_perf_5d, avg_perf_20d)
        trend = determine_trend(avg_perf_5d, avg_perf_20d)

        # Store for ranking
        all_performances.append(avg_perf_20d)

        industry_data.append({
            'sector': sector,
            'industry': industry,
            'industry_key': info['industry_key'],
            'stock_count': len(stock_performances),
            'stock_symbols': [s['symbol'] for s in stock_performances],
            'avg_change_percent': float(avg_change_percent),
            'median_change_percent': float(median_change_percent),
            'total_volume': int(total_volume),
            'avg_volume': int(total_volume / len(stock_performances)),
            'performance_1d': float(avg_perf_1d),
            'performance_5d': float(avg_perf_5d),
            'performance_20d': float(avg_perf_20d),
            'rs_vs_spy': float(rs_vs_spy),
            'momentum': momentum,
            'trend': trend,
            'total_market_cap': int(total_market_cap),
            'avg_market_cap': int(total_market_cap / len(market_caps)) if market_caps else 0,
        })

        logging.info(f"  ✅ {industry}: {len(stock_performances)} stocks, Perf={avg_perf_20d:.2f}%, Momentum={momentum}")
        gc.collect()

    # Calculate RS ratings for all industries
    for ind in industry_data:
        ind['rs_rating'] = calculate_rs_rating(ind['performance_20d'], all_performances)

    # Calculate rankings
    # Overall rank by 20-day performance
    sorted_overall = sorted(industry_data, key=lambda x: x['performance_20d'], reverse=True)
    for rank, ind in enumerate(sorted_overall, 1):
        ind['overall_rank'] = rank

    # Sector rank
    by_sector = {}
    for ind in industry_data:
        sector = ind['sector']
        if sector not in by_sector:
            by_sector[sector] = []
        by_sector[sector].append(ind)

    for sector, industries in by_sector.items():
        sorted_sector = sorted(industries, key=lambda x: x['performance_20d'], reverse=True)
        for rank, ind in enumerate(sorted_sector, 1):
            ind['sector_rank'] = rank

    return industry_data


def ensure_tables(cur, conn):
    """Ensure industry_performance table exists with proper indexes"""
    logging.info("Ensuring industry_performance table with historical tracking...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS industry_performance (
            id                  SERIAL PRIMARY KEY,
            sector              VARCHAR(100) NOT NULL,
            industry            VARCHAR(100) NOT NULL,
            industry_key        VARCHAR(100),
            stock_count         INTEGER,
            stock_symbols       TEXT[],
            avg_change_percent  DOUBLE PRECISION,
            median_change_percent DOUBLE PRECISION,
            total_volume        BIGINT,
            avg_volume          BIGINT,
            performance_1d      DOUBLE PRECISION,
            performance_5d      DOUBLE PRECISION,
            performance_20d     DOUBLE PRECISION,
            rs_rating           INTEGER,
            rs_vs_spy           DOUBLE PRECISION,
            momentum            VARCHAR(20),
            trend               VARCHAR(20),
            sector_rank         INTEGER,
            overall_rank        INTEGER,
            total_market_cap    BIGINT,
            avg_market_cap      BIGINT,
            fetched_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create unique index on industry and date to allow daily updates
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_industry_perf_industry_date_unique
        ON industry_performance(industry, DATE(fetched_at));
    """)

    # Create indexes for efficient historical queries
    cur.execute("CREATE INDEX IF NOT EXISTS idx_industry_perf_industry_date ON industry_performance(industry, fetched_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_industry_perf_sector_date ON industry_performance(sector, fetched_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_industry_perf_date ON industry_performance(fetched_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_industry_perf_overall_rank ON industry_performance(overall_rank, fetched_at DESC);")

    conn.commit()
    logging.info("✅ Industry performance table ready with historical tracking")


def insert_industry_data(cur, conn, industry_data):
    """Insert industry performance data into database"""
    if not industry_data:
        logging.warning("No industry data to insert")
        return 0

    # Clear old data (keep last 60 days for trend analysis)
    cur.execute("""
        DELETE FROM industry_performance
        WHERE fetched_at < NOW() - INTERVAL '60 days'
    """)

    # Prepare rows for insertion
    rows = []
    for ind in industry_data:
        rows.append((
            ind['sector'],
            ind['industry'],
            ind['industry_key'],
            ind['stock_count'],
            ind['stock_symbols'],
            ind['avg_change_percent'],
            ind['median_change_percent'],
            ind['total_volume'],
            ind['avg_volume'],
            ind['performance_1d'],
            ind['performance_5d'],
            ind['performance_20d'],
            ind['rs_rating'],
            ind['rs_vs_spy'],
            ind['momentum'],
            ind['trend'],
            ind['sector_rank'],
            ind['overall_rank'],
            ind['total_market_cap'],
            ind['avg_market_cap'],
            datetime.now(),
        ))

    # Delete today's records first to ensure clean insert
    cur.execute("DELETE FROM industry_performance WHERE DATE(fetched_at) = CURRENT_DATE")

    # Insert data
    insert_sql = """
        INSERT INTO industry_performance (
            sector, industry, industry_key, stock_count, stock_symbols,
            avg_change_percent, median_change_percent, total_volume, avg_volume,
            performance_1d, performance_5d, performance_20d,
            rs_rating, rs_vs_spy, momentum, trend,
            sector_rank, overall_rank, total_market_cap, avg_market_cap,
            fetched_at
        ) VALUES %s
    """

    execute_values(cur, insert_sql, rows)
    conn.commit()

    logging.info(f"✅ Inserted {len(rows)} industry performance records with historical tracking")
    return len(rows)


def update_sector_rankings(cur, conn):
    """Update sector_performance table with rankings"""
    logging.info("Updating sector rankings...")

    # Calculate sector rankings based on performance_1d
    cur.execute("""
        WITH ranked AS (
            SELECT
                symbol,
                ROW_NUMBER() OVER (ORDER BY performance_1d DESC) as rank
            FROM sector_performance
        )
        UPDATE sector_performance sp
        SET sector_rank = r.rank
        FROM ranked r
        WHERE sp.symbol = r.symbol
    """)

    # Calculate RS ratings for sectors (1-99 scale)
    cur.execute("""
        WITH perf_stats AS (
            SELECT
                symbol,
                performance_20d,
                PERCENT_RANK() OVER (ORDER BY performance_20d) as percentile
            FROM sector_performance
        )
        UPDATE sector_performance sp
        SET rs_rating = GREATEST(1, LEAST(99, ROUND(ps.percentile * 100)::INTEGER))
        FROM perf_stats ps
        WHERE sp.symbol = ps.symbol
    """)

    # Calculate RS vs SPY
    cur.execute("""
        UPDATE sector_performance sp1
        SET rs_vs_spy = sp1.performance_20d - (
            SELECT performance_20d
            FROM sector_performance
            WHERE symbol = 'SPY'
            LIMIT 1
        )
        WHERE EXISTS (SELECT 1 FROM sector_performance WHERE symbol = 'SPY')
    """)

    # Determine trend
    cur.execute("""
        UPDATE sector_performance
        SET trend = CASE
            WHEN performance_5d > 1 AND performance_20d > 2 THEN 'Uptrend'
            WHEN performance_5d < -1 AND performance_20d < -2 THEN 'Downtrend'
            ELSE 'Sideways'
        END
    """)

    conn.commit()
    logging.info("✅ Sector rankings updated")


def lambda_handler(event, context):
    """Lambda handler for AWS execution"""
    logging.info(f"Starting {SCRIPT_NAME}")

    try:
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            dbname=cfg["dbname"],
        )
        conn.autocommit = False
        cur = conn.cursor()

        # Ensure tables exist with proper indexes
        ensure_tables(cur, conn)

        # Fetch SPY prices for RS calculations
        logging.info("Fetching SPY (market benchmark)...")
        spy_prices = None
        try:
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="3mo")
            if not spy_hist.empty:
                spy_prices = spy_hist['Close'].values
                logging.info(f"✅ SPY data loaded: {len(spy_prices)} days")
        except Exception as e:
            logging.warning(f"Failed to fetch SPY: {e}")

        # Calculate industry performance
        industry_data = calculate_industry_performance(cur, spy_prices)

        # Insert industry data
        inserted = insert_industry_data(cur, conn, industry_data)

        # Update sector rankings
        update_sector_rankings(cur, conn)

        # Update last_updated
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                script_name VARCHAR(255) PRIMARY KEY,
                last_run    TIMESTAMP
            );
        """)
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
        conn.commit()

        logging.info(f"✅ Industry data load complete: {inserted} industries")

        cur.close()
        conn.close()

        return {
            "success": True,
            "industries_loaded": inserted,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logging.exception(f"Unhandled error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


if __name__ == "__main__":
    lambda_handler({}, {})
