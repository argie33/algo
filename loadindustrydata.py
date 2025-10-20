#!/usr/bin/env python3
"""
Industry Performance Loader
Calculates IBD-style industry group rankings with trend analysis
Aggregates stock performance by industry within sectors

Trigger rebuild: 20251016_143500 - Populate industry performance data to AWS
"""

import gc
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from statistics import median

import numpy as np
import yfinance as yf
from psycopg2.extras import execute_values

# Import shared utilities
from lib.db import get_db_config, get_connection, update_last_updated
from lib.rankings import calculate_rs_rating

SCRIPT_NAME = "loadindustrydata.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


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

    # Create historical rankings table
    logging.info("Creating historical rankings table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS industry_ranking (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(100) NOT NULL,
            industry VARCHAR(100) NOT NULL,
            snapshot_date DATE NOT NULL,
            current_rank INT,
            rank_1w_ago INT,
            rank_4w_ago INT,
            rank_12w_ago INT,
            momentum VARCHAR(20),
            trend VARCHAR(20),
            performance_1d FLOAT,
            performance_5d FLOAT,
            performance_20d FLOAT,
            stock_count INT,
            rank_change_1w INT,
            perf_1d_1w_ago FLOAT,
            perf_5d_1w_ago FLOAT,
            perf_20d_1w_ago FLOAT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sector, industry, snapshot_date)
        );
    """)

    conn.commit()
    logging.info("✅ Industry performance and historical ranking tables ready")


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




def get_rankings_for_date(cur, target_date):
    """Get industry rankings for a specific date"""
    cur.execute("""
        SELECT DISTINCT ON (sector, industry)
            sector,
            industry,
            overall_rank,
            rs_rating,
            performance_1d,
            DATE(fetched_at) as data_date
        FROM industry_performance
        WHERE DATE(fetched_at) <= %s
        ORDER BY sector, industry, fetched_at DESC
    """, (target_date,))

    rows = cur.fetchall()
    if not rows:
        return {}

    # Create a dict: (sector, industry) -> {rank, rs_rating, perf_1d}
    rankings = {}
    for row in rows:
        key = (row[0], row[1])  # sector, industry
        rankings[key] = {
            'rank': row[2],      # overall_rank
            'rs': row[3],        # rs_rating
            'perf_1d': row[4]    # performance_1d
        }

    return rankings


def calculate_complete_historical_rankings(cur, conn):
    """Calculate rankings for every date in database - consolidates historical data"""
    logging.info("Calculating complete historical rankings for all dates...")

    try:
        # Get all unique dates in industry_performance table
        cur.execute("""
            SELECT DISTINCT DATE(fetched_at) as data_date
            FROM industry_performance
            ORDER BY data_date DESC
        """)

        all_dates = [row[0] for row in cur.fetchall()]
        logging.info(f"📊 Found {len(all_dates)} unique dates in database")
        if all_dates:
            logging.info(f"   Date range: {all_dates[-1]} to {all_dates[0]}")

        # For each date, calculate current rank and historical ranks
        for idx, current_date in enumerate(all_dates):
            if idx % 10 == 0:
                logging.info(f"  Processing date {idx+1}/{len(all_dates)}: {current_date}")

            # Get rankings for current date and 1W/4W/8W ago (changed from 12W to 8W)
            date_1w_ago = current_date - timedelta(days=7)
            date_4w_ago = current_date - timedelta(days=28)
            date_12w_ago = current_date - timedelta(days=56)  # 8 weeks = 56 days

            ranks_current = get_rankings_for_date(cur, current_date)
            ranks_1w = get_rankings_for_date(cur, date_1w_ago)
            ranks_4w = get_rankings_for_date(cur, date_4w_ago)
            ranks_12w = get_rankings_for_date(cur, date_12w_ago)

            # Get all unique industries for current date
            all_industries = set(ranks_current.keys())
            all_industries.update(ranks_1w.keys())
            all_industries.update(ranks_4w.keys())
            all_industries.update(ranks_12w.keys())

            # Insert ranking snapshot
            for sector, industry in sorted(all_industries):
                curr = ranks_current.get((sector, industry), {})
                one_w = ranks_1w.get((sector, industry), {})
                four_w = ranks_4w.get((sector, industry), {})
                twelve_w = ranks_12w.get((sector, industry), {})

                curr_rank = curr.get('rank')
                rank_1w = one_w.get('rank')
                rank_4w = four_w.get('rank')
                rank_12w = twelve_w.get('rank')

                # Calculate rank changes (positive = improved/lower number)
                change_1w = rank_1w - curr_rank if rank_1w and curr_rank else None
                change_4w = rank_4w - curr_rank if rank_4w and curr_rank else None
                change_12w = rank_12w - curr_rank if rank_12w and curr_rank else None

                try:
                    cur.execute("""
                        INSERT INTO industry_ranking
                        (sector, industry, snapshot_date, current_rank, rank_1w_ago, rank_4w_ago, rank_12w_ago,
                         momentum, trend, performance_1d, performance_5d, performance_20d, stock_count,
                         rank_change_1w, perf_1d_1w_ago, perf_5d_1w_ago, perf_20d_1w_ago)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (sector, industry, snapshot_date) DO UPDATE SET
                        current_rank = EXCLUDED.current_rank,
                        rank_1w_ago = EXCLUDED.rank_1w_ago,
                        rank_4w_ago = EXCLUDED.rank_4w_ago,
                        rank_12w_ago = EXCLUDED.rank_12w_ago,
                        rank_change_1w = EXCLUDED.rank_change_1w,
                        momentum = EXCLUDED.momentum,
                        trend = EXCLUDED.trend,
                        performance_1d = EXCLUDED.performance_1d,
                        performance_5d = EXCLUDED.performance_5d,
                        performance_20d = EXCLUDED.performance_20d,
                        stock_count = EXCLUDED.stock_count,
                        perf_1d_1w_ago = EXCLUDED.perf_1d_1w_ago,
                        perf_5d_1w_ago = EXCLUDED.perf_5d_1w_ago,
                        perf_20d_1w_ago = EXCLUDED.perf_20d_1w_ago
                    """, (
                        sector, industry, current_date,
                        curr_rank, rank_1w, rank_4w, rank_12w,
                        curr.get('momentum', 'Moderate'), curr.get('trend', 'Sideways'),
                        curr.get('perf_1d', 0), curr.get('perf_5d', 0), curr.get('perf_20d', 0),
                        curr.get('stock_count', 0),
                        change_1w, one_w.get('perf_1d'), one_w.get('perf_5d'), one_w.get('perf_20d')
                    ))
                except Exception as e:
                    pass  # Silently skip conflicts

            conn.commit()

        # Get summary stats
        cur.execute("SELECT COUNT(*) as total FROM industry_ranking_complete")
        total_records = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT snapshot_date) as dates FROM industry_ranking_complete")
        unique_dates = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT (sector, industry)) as industries FROM industry_ranking_complete")
        unique_industries = cur.fetchone()[0]

        logging.info(f"✅ Historical rankings complete!")
        logging.info(f"   Total ranking snapshots: {total_records:,}")
        logging.info(f"   Unique dates tracked: {unique_dates}")
        logging.info(f"   Unique industries: {unique_industries}")

    except Exception as e:
        logging.error(f"❌ Error calculating historical rankings: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise


def lambda_handler(event, context):
    """Lambda handler for AWS execution"""
    logging.info(f"Starting {SCRIPT_NAME}")

    try:
        conn = get_connection()
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

        # Calculate and populate historical rankings (consolidated from separate script)
        calculate_complete_historical_rankings(cur, conn)

        # Update last_updated tracking
        update_last_updated(cur, conn, SCRIPT_NAME)

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
