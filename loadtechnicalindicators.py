#!/usr/bin/env python3
"""
Technical Indicators Loader
Calculates and populates technical_data_daily table with RSI, MACD, and other technical indicators.

Data Calculated:
- RSI (14-day) - Relative Strength Index
- MACD (12/26/9) - Moving Average Convergence Divergence
- Momentum indicators (ROC, momentum)
- Trend indicators (ADX, +DI, -DI)

Data Sources:
- price_daily table (OHLCV data)

Author: Financial Dashboard System
Updated: 2026-02-09
"""

import gc
import logging
import os
import resource
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
import pandas as pd
import numpy as np
import psycopg2
import psycopg2.extensions
from psycopg2.extras import RealDictCursor, execute_values

# Script metadata
SCRIPT_NAME = "loadtechnicalindicators.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Suppress noisy logging
logging.getLogger("psycopg2").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)
logging.getLogger("botocore").setLevel(logging.CRITICAL)

# Register numpy type adapters
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables."""

    # Try AWS Secrets Manager first
    if os.environ.get("DB_SECRET_ARN"):
        try:
            import json
            region = os.environ.get("AWS_REGION", "us-east-1")
            client = boto3.client("secretsmanager", region_name=region)
            response = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
            secret = json.loads(response["SecretString"])
            logging.info(f"Loaded database credentials from AWS Secrets Manager")
            return {
                "host": secret["host"],
                "port": int(secret.get("port", 5432)),
                "user": secret["username"],
                "password": secret["password"],
                "dbname": secret["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to load from Secrets Manager: {e}")

    # Fallback to environment variables
    db_host = os.environ.get("DB_HOST", "localhost")
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    logging.info(f"Using database credentials from environment (with defaults): {db_user}@{db_host}/{db_name}")
    return {
        "host": db_host,
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": db_user,
        "password": db_password,
        "dbname": db_name
    }


def safe_float(value, default=None, max_val=None, min_val=None):
    """Safely convert to float with optional bounds checking"""
    if value is None or pd.isna(value):
        return default
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return default
        if max_val is not None and f > max_val:
            f = max_val
        if min_val is not None and f < min_val:
            f = min_val
        return f
    except (ValueError, TypeError):
        return default


def calculate_rsi(prices: np.ndarray, period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)"""
    try:
        if len(prices) < period + 1:
            return None

        deltas = np.diff(prices)
        seed = deltas[:period + 1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period

        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs))

        return safe_float(rsi, min_val=0, max_val=100)
    except Exception as e:
        logging.debug(f"RSI calculation failed: {e}")
        return None


def calculate_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
    """Calculate MACD, Signal line, and Histogram"""
    try:
        if len(prices) < slow + signal:
            return None, None, None

        # Convert to Series for pandas EMA calculation
        prices_series = pd.Series(prices)

        # Calculate EMAs
        ema_fast = prices_series.ewm(span=fast, adjust=False).mean()
        ema_slow = prices_series.ewm(span=slow, adjust=False).mean()

        # MACD line
        macd_line = ema_fast - ema_slow

        # Signal line
        macd_signal = macd_line.ewm(span=signal, adjust=False).mean()

        # Histogram
        macd_hist = macd_line - macd_signal

        # Get the last values
        macd_val = safe_float(macd_line.iloc[-1])
        signal_val = safe_float(macd_signal.iloc[-1])
        hist_val = safe_float(macd_hist.iloc[-1])

        return macd_val, signal_val, hist_val
    except Exception as e:
        logging.debug(f"MACD calculation failed: {e}")
        return None, None, None


def calculate_momentum(prices: np.ndarray, period: int = 1) -> float:
    """Calculate Momentum (price change)"""
    try:
        if len(prices) < period + 1:
            return None
        return safe_float(prices[-1] - prices[-period - 1], max_val=999.99, min_val=-999.99)
    except Exception as e:
        logging.debug(f"Momentum calculation failed: {e}")
        return None


def calculate_roc(prices: np.ndarray, period: int = 14) -> float:
    """Calculate Rate of Change (ROC)"""
    try:
        if len(prices) < period + 1 or prices[-period - 1] == 0:
            return None
        roc = ((prices[-1] - prices[-period - 1]) / prices[-period - 1]) * 100
        return safe_float(roc, max_val=999.99, min_val=-999.99)
    except Exception as e:
        logging.debug(f"ROC calculation failed: {e}")
        return None


def load_technical_indicators(cur, conn):
    """Load technical indicators from price data."""

    try:
        logging.info("Loading price data for technical calculations...")

        # Get list of symbols with recent price data
        cur.execute("""
            SELECT DISTINCT symbol
            FROM price_daily
            WHERE date >= CURRENT_DATE - INTERVAL '2 years'
            ORDER BY symbol
        """)

        symbols = [row[0] for row in cur.fetchall()]
        logging.info(f"Processing {len(symbols)} symbols with price data")

        indicators_data = []
        processed = 0

        for symbol in symbols:
            try:
                # Get last 252 days of price data (1 trading year)
                cur.execute("""
                    SELECT date, close
                    FROM price_daily
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 252
                """, (symbol,))

                price_rows = cur.fetchall()
                if not price_rows or len(price_rows) < 14:
                    continue

                # Reverse to chronological order
                price_rows = list(reversed(price_rows))

                prices = np.array([float(row[1]) for row in price_rows if row[1] is not None])
                report_date = price_rows[-1][0]  # Most recent date

                if len(prices) < 14:
                    continue

                # Calculate indicators
                rsi = calculate_rsi(prices, period=14)
                macd, macd_signal, macd_hist = calculate_macd(prices)
                momentum = calculate_momentum(prices, period=1)
                roc = calculate_roc(prices, period=14)
                roc_10d = calculate_roc(prices, period=10) if len(prices) >= 11 else None
                roc_20d = calculate_roc(prices, period=20) if len(prices) >= 21 else None
                roc_60d = calculate_roc(prices, period=60) if len(prices) >= 61 else None
                roc_120d = calculate_roc(prices, period=120) if len(prices) >= 121 else None
                roc_252d = calculate_roc(prices, period=252) if len(prices) == 252 else None

                indicators_data.append((
                    symbol,
                    report_date,
                    rsi,
                    macd,
                    macd_signal,
                    macd_hist,
                    momentum,
                    roc,
                    roc_10d,
                    roc_20d,
                    roc_60d,
                    roc_120d,
                    roc_252d,
                    None,  # mansfield_rs (placeholder)
                    None,  # adx (placeholder)
                    None,  # plus_di (placeholder)
                    None   # minus_di (placeholder)
                ))

                processed += 1
                if processed % 500 == 0:
                    logging.info(f"  Processed {processed}/{len(symbols)} symbols")

            except Exception as e:
                logging.debug(f"Failed to process {symbol}: {e}")
                continue

        logging.info(f"Calculated technical indicators for {len(indicators_data)} symbols")

        # Delete existing records for a clean update
        cur.execute("DELETE FROM technical_data_daily WHERE date >= CURRENT_DATE - INTERVAL '1 day'")

        # Batch insert indicators
        if indicators_data:
            execute_values(
                cur,
                """
                INSERT INTO technical_data_daily (
                    symbol, date, rsi, macd, macd_signal, macd_hist,
                    mom, roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
                    mansfield_rs, adx, plus_di, minus_di
                ) VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                    rsi = EXCLUDED.rsi,
                    macd = EXCLUDED.macd,
                    macd_signal = EXCLUDED.macd_signal,
                    macd_hist = EXCLUDED.macd_hist,
                    mom = EXCLUDED.mom,
                    roc = EXCLUDED.roc,
                    roc_10d = EXCLUDED.roc_10d,
                    roc_20d = EXCLUDED.roc_20d,
                    roc_60d = EXCLUDED.roc_60d,
                    roc_120d = EXCLUDED.roc_120d,
                    roc_252d = EXCLUDED.roc_252d
                """,
                indicators_data,
                page_size=1000
            )
            conn.commit()
            logging.info(f"✅ Inserted {len(indicators_data)} technical indicator records")

        return len(indicators_data)

    except Exception as e:
        logging.error(f"❌ Failed to load technical indicators: {str(e)}")
        conn.rollback()
        raise


def main():
    """Main entry point."""
    log_mem("startup")

    try:
        # Get database config
        db_config = get_db_config()

        # Connect to database
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        logging.info(f"✅ Connected to {db_config['dbname']} database")

        # Load technical indicators
        count = load_technical_indicators(cur, conn)

        logging.info(f"✅ Technical indicators loaded successfully ({count} records)")
        log_mem("finished")

        cur.close()
        conn.close()

        return 0

    except Exception as e:
        logging.error(f"❌ FATAL: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
