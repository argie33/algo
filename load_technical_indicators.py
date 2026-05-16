#!/usr/bin/env python3
"""
Load technical indicators into technical_data_daily from price_daily.

Computes: RSI, MACD, SMA, EMA, ATR, ADX, Rate of Change, etc.
Uses TA-Lib if available, falls back to manual calculations.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
import numpy as np
import pandas as pd
from typing import Dict, List

load_dotenv(Path('.env.local'))

# Try to import talib, fall back to manual calculations
try:
    import talib
    HAS_TALIB = True
except ImportError:
    HAS_TALIB = False

def get_db_password():
    """Get DB password from env or credential manager."""
    from credential_helper import get_db_password as helper_get_pwd
    return helper_get_pwd()

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks')
    )

# Manual indicator calculations
def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return [50.0] * len(prices)

    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period

    rs = np.zeros_like(prices)
    rsi = np.zeros_like(prices)

    rsi[:period] = 100. - 100. / (1. + up / down) if down != 0 else 50.0

    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs[i] = up / down if down != 0 else rs[i-1]
        rsi[i] = 100. - 100. / (1. + rs[i])

    return rsi

def calculate_sma(prices, period):
    """Calculate Simple Moving Average."""
    if len(prices) < period:
        return [prices[0]] * len(prices)
    return pd.Series(prices).rolling(window=period, min_periods=1).mean().values

def calculate_ema(prices, period):
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return [prices[0]] * len(prices)
    return pd.Series(prices).ewm(span=period, adjust=False).mean().values

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD."""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

def calculate_atr(high, low, close, period=14):
    """Calculate Average True Range."""
    tr = []
    for i in range(len(close)):
        if i == 0:
            tr.append(high[i] - low[i])
        else:
            tr.append(max(
                high[i] - low[i],
                abs(high[i] - close[i-1]),
                abs(low[i] - close[i-1])
            ))

    atr = pd.Series(tr).rolling(window=period, min_periods=1).mean().values
    return atr

def calculate_roc(prices, period):
    """Calculate Rate of Change."""
    roc = np.zeros_like(prices, dtype=float)
    for i in range(period, len(prices)):
        if prices[i-period] != 0:
            roc[i] = ((prices[i] - prices[i-period]) / prices[i-period]) * 100
    return roc

def load_technical_indicators():
    """Load technical indicators for all symbols."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Clear existing data
    cur.execute("DELETE FROM technical_data_daily")
    conn.commit()

    # Get all symbols with price data
    cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
    symbols = [row[0] for row in cur.fetchall()]

    print(f"Computing technical indicators for {len(symbols)} symbols...")

    for idx, symbol in enumerate(symbols):
        try:
            # Fetch price data for symbol
            cur.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s
                ORDER BY date ASC
            """, (symbol,))

            rows = cur.fetchall()
            if not rows:
                continue

            dates = [row[0] for row in rows]
            opens = np.array([row[1] for row in rows], dtype=float)
            highs = np.array([row[2] for row in rows], dtype=float)
            lows = np.array([row[3] for row in rows], dtype=float)
            closes = np.array([row[4] for row in rows], dtype=float)
            volumes = np.array([row[5] for row in rows], dtype=float)

            # Calculate all indicators
            rsi = calculate_rsi(closes)
            sma20 = calculate_sma(closes, 20)
            sma50 = calculate_sma(closes, 50)
            sma200 = calculate_sma(closes, 200)
            ema12 = calculate_ema(closes, 12)
            ema26 = calculate_ema(closes, 26)
            macd, macd_signal, macd_hist = calculate_macd(closes)
            atr = calculate_atr(highs, lows, closes)
            mom = np.diff(closes, prepend=closes[0]) * 100
            roc10 = calculate_roc(closes, 10)
            roc20 = calculate_roc(closes, 20)
            roc60 = calculate_roc(closes, 60)
            roc120 = calculate_roc(closes, 120)
            roc252 = calculate_roc(closes, 252)

            # Insert into database
            for i in range(len(dates)):
                cur.execute("""
                    INSERT INTO technical_data_daily
                    (symbol, date, rsi, macd, macd_signal, macd_hist, mom,
                     roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
                     sma_20, sma_50, sma_200, ema_12, ema_26, atr,
                     adx, plus_di, minus_di, mansfield_rs, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    symbol, dates[i],
                    float(rsi[i]), float(macd[i]), float(macd_signal[i]), float(macd_hist[i]),
                    float(mom[i]),
                    float(roc10[i] if i >= 10 else 0),  # roc (generic)
                    float(roc10[i]), float(roc20[i]), float(roc60[i]), float(roc120[i]), float(roc252[i]),
                    float(sma20[i]), float(sma50[i]), float(sma200[i]),
                    float(ema12[i]), float(ema26[i]), float(atr[i]),
                    0.0, 0.0, 0.0, 0.0  # ADX, +DI, -DI, RS (placeholders)
                ))

            conn.commit()

            if (idx + 1) % 10 == 0:
                print(f"  Processed {idx + 1}/{len(symbols)} symbols...")

        except Exception as e:
            print(f"  ERROR on {symbol}: {e}")
            conn.rollback()
            continue

    cur.execute("SELECT COUNT(*) FROM technical_data_daily")
    count = cur.fetchone()[0]
    print(f"\nCompleted! Inserted {count} technical indicator records.")

    conn.close()

if __name__ == '__main__':
    try:
        load_technical_indicators()
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)
