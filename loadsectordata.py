#!/usr/bin/env python3
# Updated: 2025-10-16 14:32 - Trigger rebuild: 20251016_143300 - Populate sector performance data to AWS
"""
Sector Data Loader
Loads sector ETF performance data from yfinance for sector rotation analysis
Tracks momentum, money flow, and performance metrics for 11 major sectors
"""
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

import boto3
import numpy as np
import psycopg2
import yfinance as yf
from psycopg2.extras import execute_values

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


def get_db_config():
    """Fetch database credentials from AWS Secrets Manager or use local environment"""
    # Check if running locally
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


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def calculate_relative_strength(sector_prices, spy_prices):
    """
    Calculate relative strength vs SPY (market)
    Returns percentage outperformance/underperformance
    """
    if len(sector_prices) < 20 or len(spy_prices) < 20:
        return 0

    # 20-day performance
    sector_perf = ((sector_prices[-1] - sector_prices[-20]) / sector_prices[-20]) * 100
    spy_perf = ((spy_prices[-1] - spy_prices[-20]) / spy_prices[-20]) * 100

    return round(sector_perf - spy_perf, 2)


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


def calculate_money_flow(volume, prices):
    """
    Calculate money flow (Inflow/Outflow/Neutral)
    Based on Chaikin Money Flow indicator
    """
    if len(volume) < 20 or len(prices) < 20:
        return "Neutral"

    # Simple approach: compare volume on up days vs down days
    recent_vol = volume[-20:]
    recent_prices = prices[-20:]

    up_volume = 0
    down_volume = 0

    for i in range(1, len(recent_prices)):
        if recent_prices[i] > recent_prices[i-1]:
            up_volume += recent_vol[i]
        elif recent_prices[i] < recent_prices[i-1]:
            down_volume += recent_vol[i]

    total_volume = up_volume + down_volume
    if total_volume == 0:
        return "Neutral"

    # Calculate ratio
    ratio = up_volume / total_volume

    if ratio > 0.55:  # More than 55% volume on up days
        return "Inflow"
    elif ratio < 0.45:  # Less than 45% volume on up days
        return "Outflow"
    else:
        return "Neutral"


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

        # Calculate relative strength vs market (SPY)
        relative_strength = 0
        if spy_prices is not None:
            relative_strength = calculate_relative_strength(prices, spy_prices)

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
            'relative_strength': float(relative_strength),
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
            relative_strength   DOUBLE PRECISION,
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
                data['relative_strength'],
                data['performance_1d'],
                data['performance_5d'],
                data['performance_20d'],
                data['sma_50'],
                data['sma_200'],
                None,  # sector_rank will be calculated after insert
                datetime.now(),
            ))
            logging.info(f"  ✅ {symbol}: RSI={data['rsi']}, RS={data['relative_strength']:.2f}%, Momentum={data['momentum']}")
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
                volume, total_assets, momentum, money_flow, rsi, relative_strength,
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

        # Create table
        create_table(cur)
        conn.commit()

        # Load sector data
        success, failed = load_sector_data(cur, conn)

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
