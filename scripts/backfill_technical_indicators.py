#!/usr/bin/env python3
"""Direct backfill of technical indicators for all symbols missing RSI/MACD/ROC.

Bypasses loader watermarks to populate momentum_metrics for all symbols.
"""

import sys
sys.path.insert(0, '.')

from utils.dotenv_loader import load_env_local
load_env_local()

import psycopg2
import os
import logging
from datetime import date, datetime, timezone
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def get_price_history(cur, symbol, limit=252):
    """Get recent price history for a symbol."""
    cur.execute(
        'SELECT date, close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT %s',
        (symbol, limit)
    )
    rows = cur.fetchall()
    if not rows:
        return None
    rows = sorted(rows, key=lambda x: x[0])  # Sort ascending by date
    dates = [r[0] for r in rows]
    prices = np.array([float(r[1]) for r in rows])
    return dates, prices

def calculate_rsi(prices, period=14):
    """Calculate RSI."""
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = 100. - 100. / (1. + rs)

    for d in deltas[period+1:]:
        if d >= 0:
            up = (up * (period - 1) + d) / period
            down = (down * (period - 1)) / period
        else:
            up = (up * (period - 1)) / period
            down = (down * (period - 1) - d) / period
        rs = up / down if down != 0 else 0
        rsi = 100. - 100. / (1. + rs)

    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD line."""
    if len(prices) < slow:
        return None

    ema_fast = prices[-fast:].mean()
    ema_slow = prices[-slow:].mean()

    for i in range(len(prices) - slow, len(prices)):
        ema_slow = prices[i] * (2 / (slow + 1)) + ema_slow * (1 - 2 / (slow + 1))
    for i in range(len(prices) - fast, len(prices)):
        ema_fast = prices[i] * (2 / (fast + 1)) + ema_fast * (1 - 2 / (fast + 1))

    macd = ema_fast - ema_slow
    return macd

def calculate_roc(prices, period):
    """Calculate Rate of Change."""
    if len(prices) <= period:
        return None
    if prices[-period] == 0:
        return None
    roc = ((prices[-1] - prices[-period]) / prices[-period]) * 100
    return roc

def backfill_symbol(cur_read, cur_write, symbol):
    """Calculate and insert technical indicators for a symbol."""
    try:
        # Get price history
        price_data = get_price_history(cur_read, symbol)
        if not price_data:
            return False

        dates, prices = price_data

        # Calculate indicators
        rsi = calculate_rsi(prices)
        macd = calculate_macd(prices)
        roc_20d = calculate_roc(prices, 20) if len(prices) > 20 else None
        roc_60d = calculate_roc(prices, 60) if len(prices) > 60 else None
        roc_120d = calculate_roc(prices, 120) if len(prices) > 120 else None
        roc_252d = calculate_roc(prices, 252) if len(prices) > 252 else None

        # Check if record exists
        cur_read.execute('SELECT 1 FROM momentum_metrics WHERE symbol = %s', (symbol,))
        exists = cur_read.fetchone()

        if exists:
            # Update existing record
            cur_write.execute('''
                UPDATE momentum_metrics
                SET rsi_14 = %s, macd_line = %s, roc_20d = %s, roc_60d = %s,
                    roc_120d = %s, roc_252d = %s
                WHERE symbol = %s
            ''', (rsi, macd, roc_20d, roc_60d, roc_120d, roc_252d, symbol))
        else:
            # Insert new record with minimal data
            cur_write.execute('''
                INSERT INTO momentum_metrics (symbol, rsi_14, macd_line, roc_20d, roc_60d, roc_120d, roc_252d, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (symbol, rsi, macd, roc_20d, roc_60d, roc_120d, roc_252d,
                  datetime.now(timezone.utc).isoformat()))

        return True
    except Exception as e:
        logger.warning(f"Failed to backfill {symbol}: {e}")
        return False

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT', 5432),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

cur_read = conn.cursor()
cur_write = conn.cursor()

try:
    # Get all symbols
    cur_read.execute('SELECT DISTINCT symbol FROM stock_scores ORDER BY symbol')
    symbols = [row[0] for row in cur_read.fetchall()]

    print(f"Backfilling {len(symbols)} symbols...")
    success_count = 0

    for i, symbol in enumerate(symbols):
        if backfill_symbol(cur_read, cur_write, symbol):
            success_count += 1

        if (i + 1) % 100 == 0:
            conn.commit()
            print(f"  Processed {i + 1}/{len(symbols)} ({success_count} successful)")

    conn.commit()
    print(f"Backfill complete: {success_count}/{len(symbols)} symbols populated")

finally:
    cur_read.close()
    cur_write.close()
    conn.close()
