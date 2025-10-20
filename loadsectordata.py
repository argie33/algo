#!/usr/bin/env python3
# Updated: 2025-10-16 14:32 - Trigger rebuild: 20251016_143300 - Populate sector performance data to AWS
"""
Sector Data Loader
Loads sector ETF performance data from yfinance for sector rotation analysis
Tracks momentum, money flow, and performance metrics for 11 major sectors
"""
import gc
import logging
import os
import sys
import time
from datetime import datetime

import numpy as np
import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

# Import shared utilities
from lib.db import get_db_config, get_connection, update_last_updated
from lib.performance import calculate_rsi, calculate_performance_metrics, calculate_moving_averages, calculate_money_flow

SCRIPT_NAME = "loadsectordata.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Sector ETF mapping - 11 major sectors
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}


def calculate_momentum(prices):
    """
    Calculate momentum indicator (Strong/Moderate/Weak)
    Based on 20-day and 50-day moving average relationship + price action
    """
    if len(prices) < 50:
        return "Moderate"

    sma_20 = np.mean(prices[-20:])
    sma_50 = np.mean(prices[-50:])
    current = prices[-1]

    # Also check recent momentum (5-day vs 10-day)
    sma_5 = np.mean(prices[-5:]) if len(prices) >= 5 else current
    sma_10 = np.mean(prices[-10:]) if len(prices) >= 10 else current

    # Strong: Price above both MAs, 20 > 50, and accelerating
    if current > sma_20 > sma_50 and sma_5 > sma_10:
        return "Strong"
    # Weak: Price below both MAs, 20 < 50, and decelerating
    elif current < sma_20 < sma_50 and sma_5 < sma_10:
        return "Weak"
    else:
        return "Moderate"


def fetch_sector_data(symbol, sector_name, spy_prices=None):
    """Fetch sector ETF data from yfinance"""
    try:
        ticker = yf.Ticker(symbol)

        # Get 90 days of history for momentum/flow calculations
        hist = ticker.history(period="3mo")
        if hist.empty or len(hist) < 5:
            logging.warning(f"No data for {symbol}")
            return None

        # Get current quote
        info = ticker.info

        # Calculate metrics
        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        change = current_price - prev_price
        change_percent = (change / prev_price) * 100

        # Get volume and assets under management
        volume = int(hist['Volume'].iloc[-1])
        total_assets = info.get('totalAssets', None)  # AUM for ETFs

        # Calculate momentum and money flow
        prices = hist['Close'].values
        volumes = hist['Volume'].values

        momentum = calculate_momentum(prices)
        flow = calculate_money_flow(volumes, prices)

        # Calculate RSI
        rsi = calculate_rsi(prices)

        # Calculate performance (1-day, 5-day, 20-day)
        perf_1d = change_percent
        perf_5d = ((current_price - hist['Close'].iloc[-6]) / hist['Close'].iloc[-6] * 100) if len(hist) >= 6 else 0
        perf_20d = ((current_price - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21] * 100) if len(hist) >= 21 else 0

        # Calculate 50-day and 200-day SMAs
        sma_50 = float(np.mean(prices[-50:])) if len(prices) >= 50 else None
        sma_200 = float(np.mean(prices[-200:])) if len(prices) >= 200 else None

        return {
            'symbol': symbol,
            'sector_name': sector_name,
            'price': float(current_price),
            'change': float(change),
            'change_percent': float(change_percent),
            'volume': int(volume),
            'total_assets': int(total_assets) if total_assets is not None else None,
            'momentum': momentum,
            'money_flow': flow,
            'rsi': float(rsi) if rsi is not None else None,
            'performance_1d': float(perf_1d),
            'performance_5d': float(perf_5d),
            'performance_20d': float(perf_20d),
            'sma_50': sma_50,
            'sma_200': sma_200,
        }

    except Exception as e:
        logging.error(f"Failed to fetch {symbol} ({sector_name}): {e}")
        return None


def create_table(cur):
    """Create sector_performance table with history tracking"""
    logging.info("Creating sector_performance table with historical tracking...")

    # Use CREATE TABLE IF NOT EXISTS to preserve history
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_performance (
            id                  SERIAL PRIMARY KEY,
            symbol              VARCHAR(20) NOT NULL,
            sector_name         VARCHAR(100) NOT NULL,
            price               DOUBLE PRECISION,
            change              DOUBLE PRECISION,
            change_percent      DOUBLE PRECISION,
            volume              BIGINT,
            total_assets        BIGINT,
            momentum            VARCHAR(20),
            money_flow          VARCHAR(20),
            rsi                 DOUBLE PRECISION,
            performance_1d      DOUBLE PRECISION,
            performance_5d      DOUBLE PRECISION,
            performance_20d     DOUBLE PRECISION,
            sma_50              DOUBLE PRECISION,
            sma_200             DOUBLE PRECISION,
            sector_rank         INTEGER,
            fetched_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create unique index on symbol and date to allow daily updates
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_performance_symbol_date_unique
        ON sector_performance(symbol, DATE(fetched_at));
    """)

    # Create indexes for fast lookups and historical queries
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_performance_symbol_date
        ON sector_performance(symbol, fetched_at DESC);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_performance_date
        ON sector_performance(fetched_at DESC);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_performance_sector_date
        ON sector_performance(sector_name, fetched_at DESC);
    """)

    logging.info("Table 'sector_performance' ready with history tracking")


def create_sector_ranking_table(cur):
    """Create sector_ranking table for historical sector ranking snapshots"""
    logging.info("Creating sector_ranking table with historical ranking data...")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_ranking (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(100) NOT NULL,
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
            UNIQUE(sector, snapshot_date)
        );
    """)

    # Create indexes for fast lookups
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_ranking_sector_date
        ON sector_ranking(sector, snapshot_date DESC);
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_ranking_date
        ON sector_ranking(snapshot_date DESC);
    """)

    logging.info("Table 'sector_ranking' ready with historical ranking support")


def load_sector_data(cur, conn):
    """Load data for all sector ETFs"""
    logging.info(f"Loading {len(SECTOR_ETFS)} sector ETFs...")

    # First, fetch SPY for relative strength calculations
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

    data_rows = []
    success_count = 0
    failed_count = 0

    for symbol, sector_name in SECTOR_ETFS.items():
        logging.info(f"Fetching {symbol} ({sector_name})...")

        data = fetch_sector_data(symbol, sector_name, spy_prices)

        if data:
            data_rows.append((
                data['symbol'],
                data['sector_name'],
                data['price'],
                data['change'],
                data['change_percent'],
                data['volume'],
                data['total_assets'],
                data['momentum'],
                data['money_flow'],
                data['rsi'],
                data['performance_1d'],
                data['performance_5d'],
                data['performance_20d'],
                data['sma_50'],
                data['sma_200'],
                None,  # sector_rank will be calculated after insert
                datetime.now(),
            ))
            logging.info(f"  ✅ {symbol}: RSI={data['rsi']}, Momentum={data['momentum']}")
            success_count += 1
        else:
            failed_count += 1

        # Rate limiting
        time.sleep(0.5)
        gc.collect()

    # Insert all data
    if data_rows:
        # Delete today's records first to ensure clean insert
        cur.execute("DELETE FROM sector_performance WHERE DATE(fetched_at) = CURRENT_DATE")

        insert_sql = """
            INSERT INTO sector_performance (
                symbol, sector_name, price, change, change_percent,
                volume, total_assets, momentum, money_flow, rsi,
                performance_1d, performance_5d, performance_20d,
                sma_50, sma_200, sector_rank, fetched_at
            ) VALUES %s
        """
        execute_values(cur, insert_sql, data_rows)

        # Calculate rankings for today
        cur.execute("""
            UPDATE sector_performance sp SET
                sector_rank = ranked.rank
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (ORDER BY performance_20d DESC) as rank
                FROM sector_performance
                WHERE DATE(fetched_at) = CURRENT_DATE
            ) ranked
            WHERE sp.id = ranked.id AND DATE(sp.fetched_at) = CURRENT_DATE
        """)

        conn.commit()
        logging.info(f"✅ Inserted {len(data_rows)} sector records with historical tracking")

    return success_count, failed_count


def lambda_handler(event, context):
    """Lambda handler for AWS execution"""
    logging.info(f"Starting {SCRIPT_NAME}")

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Create tables
        create_table(cur)
        create_sector_ranking_table(cur)
        conn.commit()

        # Load sector data
        success, failed = load_sector_data(cur, conn)

        # Update last_updated tracking
        update_last_updated(cur, conn, SCRIPT_NAME)

        logging.info(f"Summary: Success={success}, Failed={failed}")
        logging.info("✅ Sector data load complete")

        cur.close()
        conn.close()

        return {
            "success": success,
            "failed": failed,
            "total": len(SECTOR_ETFS)
        }

    except Exception as e:
        logging.exception(f"Unhandled error: {e}")
        return {
            "success": 0,
            "failed": len(SECTOR_ETFS),
            "error": str(e)
        }


if __name__ == "__main__":
    lambda_handler({}, {})
# Trigger rebuild 20251016_143300
