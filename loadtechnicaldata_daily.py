#!/usr/bin/env python3
"""
Technical Data Daily Loader
Calculates and updates technical indicators (RSI, MACD, SMA, EMA, ATR, ADX, etc.) for all stocks
Required by frontend for scores API (RSI, MACD used in momentum calculations)
"""

import sys
import time
import logging
import json
import os
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import boto3
from db_helper import get_db_connection

# Configure logging
SCRIPT_NAME = "loadtechnicaldata_daily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# Database configuration
DB_SECRET_ARN = os.getenv('DB_SECRET_ARN')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'bed0elAn')
DB_NAME = os.getenv('DB_NAME', 'stocks')

def get_db_connection():
    """Get database connection with AWS fallback"""
    if DB_SECRET_ARN:
        try:
            secret_str = boto3.client("secretsmanager", region_name="us-east-1") \
                             .get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"]
            sec = json.loads(secret_str)
            cfg = {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to fetch from AWS Secrets Manager: {e}, falling back to environment variables")
            cfg = {
                "host": DB_HOST,
                "port": int(DB_PORT),
                "user": DB_USER,
                "password": DB_PASSWORD,
                "dbname": DB_NAME
            }
    else:
        cfg = {
            "host": DB_HOST,
            "port": int(DB_PORT),
            "user": DB_USER,
            "password": DB_PASSWORD,
            "dbname": DB_NAME
        }

    return psycopg2.connect(**cfg)

def calculate_rsi(prices, period=14):
    """Calculate RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return None

    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100.0 - 100.0 / (1.0 + rs)

    for d in deltas[period+1:]:
        if d >= 0:
            up = (up * (period - 1) + d) / period
            down = (down * (period - 1)) / period
        else:
            up = (up * (period - 1)) / period
            down = (down * (period - 1) - d) / period

        rs = up / down if down != 0 else 0
        rsi = 100.0 - 100.0 / (1.0 + rs)

    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if len(prices) < slow:
        return None, None, None

    ema_fast = pd.Series(prices).ewm(span=fast).mean().values[-1]
    ema_slow = pd.Series(prices).ewm(span=slow).mean().values[-1]
    macd_line = ema_fast - ema_slow

    return macd_line, None, None

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    if len(prices) < period:
        return None
    return np.mean(prices[-period:])

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average"""
    if len(prices) < period:
        return None
    return pd.Series(prices).ewm(span=period).mean().values[-1]

def calculate_atr(high_prices, low_prices, close_prices, period=14):
    """Calculate Average True Range"""
    if len(high_prices) < period:
        return None

    tr = []
    for i in range(len(high_prices)):
        if i == 0:
            tr_val = high_prices[i] - low_prices[i]
        else:
            tr_val = max(
                high_prices[i] - low_prices[i],
                abs(high_prices[i] - close_prices[i-1]),
                abs(low_prices[i] - close_prices[i-1])
            )
        tr.append(tr_val)

    return np.mean(tr[-period:])

def calculate_adx(high_prices, low_prices, close_prices, period=14):
    """Calculate ADX (Average Directional Index) - simplified"""
    if len(high_prices) < period + 1:
        return None

    plus_dm = np.maximum(high_prices[1:] - high_prices[:-1], 0)
    minus_dm = np.maximum(low_prices[:-1] - low_prices[1:], 0)

    tr = []
    for i in range(len(high_prices) - 1):
        tr_val = max(
            high_prices[i+1] - low_prices[i+1],
            abs(high_prices[i+1] - close_prices[i]),
            abs(low_prices[i+1] - close_prices[i])
        )
        tr.append(tr_val)

    atr_val = np.mean(tr[-period:]) if len(tr) >= period else None
    if atr_val is None or atr_val == 0:
        return None

    plus_di = 100 * np.mean(plus_dm[-period:]) / atr_val
    minus_di = 100 * np.mean(minus_dm[-period:]) / atr_val
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) != 0 else 0

    return np.mean([dx] * min(period, len([dx])))

def calculate_roc(prices, period):
    """Calculate Rate of Change"""
    if len(prices) < period + 1:
        return None

    return ((prices[-1] - prices[-period-1]) / prices[-period-1]) * 100 if prices[-period-1] != 0 else None

def calculate_momentum(prices, period=10):
    """Calculate Momentum"""
    if len(prices) < period + 1:
        return None

    return prices[-1] - prices[-period-1]

def load_technical_data():
    """Load and calculate technical data for all symbols"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get all symbols
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols WHERE symbol NOT LIKE '%$%' ORDER BY symbol;")
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Calculating technical indicators for {len(symbols)} symbols")

        processed = 0
        failed = []

        for symbol in symbols:
            try:
                # Get price data
                cur.execute("""
                    SELECT date, open, high, low, close, volume
                    FROM price_daily
                    WHERE symbol = %s
                    ORDER BY date DESC
                    LIMIT 252
                """, (symbol,))

                rows = cur.fetchall()
                if not rows:
                    continue

                # Reverse to get chronological order
                rows = list(reversed(rows))

                df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')

                if len(df) < 20:
                    continue

                # Get latest date's indicators
                latest_date = df['date'].iloc[-1]
                close_prices = df['close'].values.astype(float)
                high_prices = df['high'].values.astype(float)
                low_prices = df['low'].values.astype(float)

                # Helper to convert to float safely
                def safe_float(val):
                    if val is None:
                        return None
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return None

                # Calculate indicators
                rsi = safe_float(calculate_rsi(close_prices))
                macd_val, macd_signal, macd_hist = calculate_macd(close_prices)
                macd = safe_float(macd_val)
                mom = safe_float(calculate_momentum(close_prices))
                roc = safe_float(calculate_roc(close_prices, 10))
                roc_20d = safe_float(calculate_roc(close_prices, 20))
                roc_60d = safe_float(calculate_roc(close_prices, 60))
                roc_120d = safe_float(calculate_roc(close_prices, 120))
                roc_252d = safe_float(calculate_roc(close_prices, 252))

                atr = safe_float(calculate_atr(high_prices, low_prices, close_prices))
                adx = safe_float(calculate_adx(high_prices, low_prices, close_prices))

                sma_10 = safe_float(calculate_sma(close_prices, 10))
                sma_20 = safe_float(calculate_sma(close_prices, 20))
                sma_50 = safe_float(calculate_sma(close_prices, 50))
                sma_150 = safe_float(calculate_sma(close_prices, 150))
                sma_200 = safe_float(calculate_sma(close_prices, 200))

                ema_4 = safe_float(calculate_ema(close_prices, 4))
                ema_9 = safe_float(calculate_ema(close_prices, 9))
                ema_21 = safe_float(calculate_ema(close_prices, 21))

                # Bollinger Bands
                if len(df) >= 20 and sma_20 is not None:
                    std = float(np.std(close_prices[-20:]))
                    bbands_lower = safe_float(sma_20 - (std * 2))
                    bbands_middle = sma_20
                    bbands_upper = safe_float(sma_20 + (std * 2))
                else:
                    bbands_lower = None
                    bbands_middle = None
                    bbands_upper = None

                # Insert or update
                cur.execute("""
                    INSERT INTO technical_data_daily (
                        symbol, date, rsi, macd, macd_signal, macd_hist, mom, roc,
                        roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
                        atr, adx, sma_10, sma_20, sma_50, sma_150, sma_200,
                        ema_4, ema_9, ema_21, bbands_lower, bbands_middle, bbands_upper
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        roc_252d = EXCLUDED.roc_252d,
                        atr = EXCLUDED.atr,
                        adx = EXCLUDED.adx,
                        sma_10 = EXCLUDED.sma_10,
                        sma_20 = EXCLUDED.sma_20,
                        sma_50 = EXCLUDED.sma_50,
                        sma_150 = EXCLUDED.sma_150,
                        sma_200 = EXCLUDED.sma_200,
                        ema_4 = EXCLUDED.ema_4,
                        ema_9 = EXCLUDED.ema_9,
                        ema_21 = EXCLUDED.ema_21,
                        bbands_lower = EXCLUDED.bbands_lower,
                        bbands_middle = EXCLUDED.bbands_middle,
                        bbands_upper = EXCLUDED.bbands_upper;
                """, (
                    symbol, latest_date, rsi, macd, macd_signal, macd_hist, mom, roc,
                    roc_20d, roc_60d, roc_120d, roc_252d, roc_252d,
                    atr, adx, sma_10, sma_20, sma_50, sma_150, sma_200,
                    ema_4, ema_9, ema_21, bbands_lower, bbands_middle, bbands_upper
                ))

                processed += 1
                if processed % 100 == 0:
                    conn.commit()
                    logging.info(f"Processed {processed} symbols")

            except Exception as e:
                logging.warning(f"Error processing {symbol}: {e}")
                failed.append(symbol)
                continue

        conn.commit()
        logging.info(f"Technical data loaded: {processed} processed, {len(failed)} failed")

    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    try:
        logging.info(f"Starting {SCRIPT_NAME}")
        load_technical_data()
        logging.info("✅ Technical data loader completed successfully")
        sys.exit(0)
    except Exception as e:
        logging.error(f"❌ Error: {e}")
        sys.exit(1)
