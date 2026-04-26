#!/usr/bin/env python3
"""
Populate technical data (RSI, MACD, SMA, EMA, ATR, ADX) for all stock and ETF symbols
across daily, weekly, and monthly timeframes.
"""
import os
import sys
import logging
import json
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
import boto3
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration from environment or AWS Secrets."""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets failed: {str(e)[:100]}")

    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")
    db_port = os.environ.get("DB_PORT", "5432")

    if db_host and db_user and db_password and db_name:
        return {
            "host": db_host,
            "port": int(db_port),
            "user": db_user,
            "password": db_password,
            "dbname": db_name
        }

    raise EnvironmentError("Cannot find database credentials")

def calculate_rsi(closes, period=14):
    """Calculate RSI (Relative Strength Index)."""
    if len(closes) < period + 1:
        return np.full(len(closes), np.nan)

    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    avg_gain = np.zeros(len(closes))
    avg_loss = np.zeros(len(closes))

    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])

    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gain[i-1]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + loss[i-1]) / period

    rs = np.divide(avg_gain, avg_loss, where=avg_loss != 0, out=np.full_like(avg_gain, np.nan))
    rsi = 100 - (100 / (1 + rs))

    return rsi

def calculate_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)."""
    ema_fast = pd.Series(closes).ewm(span=fast).mean().values
    ema_slow = pd.Series(closes).ewm(span=slow).mean().values
    macd_line = ema_fast - ema_slow
    macd_signal = pd.Series(macd_line).ewm(span=signal).mean().values
    macd_histogram = macd_line - macd_signal

    return macd_line, macd_signal, macd_histogram

def calculate_sma(closes, period):
    """Calculate SMA (Simple Moving Average)."""
    return pd.Series(closes).rolling(window=period).mean().values

def calculate_ema(closes, period):
    """Calculate EMA (Exponential Moving Average)."""
    return pd.Series(closes).ewm(span=period).mean().values

def calculate_atr(highs, lows, closes, period=14):
    """Calculate ATR (Average True Range)."""
    tr = np.maximum(
        highs - lows,
        np.maximum(
            np.abs(highs - np.roll(closes, 1)),
            np.abs(lows - np.roll(closes, 1))
        )
    )
    tr[0] = highs[0] - lows[0]
    atr = pd.Series(tr).rolling(window=period).mean().values
    return atr

def calculate_adx(highs, lows, closes, period=14):
    """Calculate ADX (Average Directional Index)."""
    plus_dm = np.maximum(highs - np.roll(highs, 1), 0)
    minus_dm = np.maximum(np.roll(lows, 1) - lows, 0)
    plus_dm[0] = 0
    minus_dm[0] = 0

    tr = np.maximum(
        highs - lows,
        np.maximum(
            np.abs(highs - np.roll(closes, 1)),
            np.abs(lows - np.roll(closes, 1))
        )
    )
    tr[0] = highs[0] - lows[0]

    atr = pd.Series(tr).rolling(window=period).mean().values

    plus_di = 100 * pd.Series(plus_dm).rolling(window=period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=period).mean() / atr
    di_diff = np.abs(plus_di - minus_di)
    di_sum = plus_di + minus_di

    dx = 100 * np.divide(di_diff, di_sum, where=di_sum != 0, out=np.full_like(di_sum, np.nan))
    adx = pd.Series(dx).rolling(window=period).mean().values

    return adx

def populate_technical_for_timeframe(conn, price_table, technical_table, timeframe="daily"):
    """Populate technical indicators for a specific timeframe."""
    cur = conn.cursor()

    # Get all symbols that have price data but no technical data
    cur.execute(f"""
        SELECT DISTINCT p.symbol
        FROM {price_table} p
        WHERE NOT EXISTS (
            SELECT 1 FROM {technical_table} t WHERE t.symbol = p.symbol
        )
        ORDER BY p.symbol
    """)
    symbols = [row[0] for row in cur.fetchall()]

    logging.info(f"Found {len(symbols)} symbols needing technical data for {timeframe}")

    processed = 0
    for symbol in symbols:
        try:
            # Fetch price data
            cur.execute(f"""
                SELECT date, open, high, low, close, volume
                FROM {price_table}
                WHERE symbol = %s
                ORDER BY date ASC
            """, (symbol,))

            rows = cur.fetchall()
            if len(rows) < 30:  # Need minimum data for indicators
                logging.debug(f"{symbol}: Only {len(rows)} rows, skipping")
                continue

            dates = [row[0] for row in rows]
            opens = np.array([row[1] for row in rows])
            highs = np.array([row[2] for row in rows])
            lows = np.array([row[3] for row in rows])
            closes = np.array([row[4] for row in rows])
            volumes = np.array([row[5] for row in rows])

            # Calculate indicators
            rsi = calculate_rsi(closes, period=14)
            macd_line, macd_signal, macd_hist = calculate_macd(closes, 12, 26, 9)
            sma_20 = calculate_sma(closes, 20)
            sma_50 = calculate_sma(closes, 50)
            sma_200 = calculate_sma(closes, 200)
            ema_12 = calculate_ema(closes, 12)
            ema_26 = calculate_ema(closes, 26)
            atr = calculate_atr(highs, lows, closes, 14)
            adx = calculate_adx(highs, lows, closes, 14)

            # Insert technical data
            data = []
            for i in range(len(dates)):
                data.append((
                    symbol, dates[i],
                    float(rsi[i]) if not np.isnan(rsi[i]) else None,
                    float(macd_line[i]) if not np.isnan(macd_line[i]) else None,
                    float(macd_signal[i]) if not np.isnan(macd_signal[i]) else None,
                    float(macd_hist[i]) if not np.isnan(macd_hist[i]) else None,
                    float(sma_20[i]) if not np.isnan(sma_20[i]) else None,
                    float(sma_50[i]) if not np.isnan(sma_50[i]) else None,
                    float(sma_200[i]) if not np.isnan(sma_200[i]) else None,
                    float(ema_12[i]) if not np.isnan(ema_12[i]) else None,
                    float(ema_26[i]) if not np.isnan(ema_26[i]) else None,
                    float(atr[i]) if not np.isnan(atr[i]) else None,
                    float(adx[i]) if not np.isnan(adx[i]) else None
                ))

            execute_values(cur, f"""
                INSERT INTO {technical_table}
                (symbol, date, rsi, macd, macd_signal, macd_histogram, sma_20, sma_50, sma_200, ema_12, ema_26, atr, adx)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, data, page_size=1000)

            conn.commit()
            processed += 1
            if processed % 100 == 0:
                logging.info(f"{timeframe}: Processed {processed}/{len(symbols)} symbols")

        except Exception as e:
            conn.rollback()
            logging.error(f"{symbol}: {str(e)[:100]}")

    logging.info(f"{timeframe}: Completed {processed} symbols")
    return processed

def main():
    config = get_db_config()
    conn = psycopg2.connect(**config)

    timeframes = [
        ("price_daily", "technical_data_daily", "daily"),
        ("price_weekly", "technical_data_weekly", "weekly"),
        ("price_monthly", "technical_data_monthly", "monthly")
    ]

    for price_table, technical_table, timeframe in timeframes:
        logging.info(f"Starting {timeframe} technical data population...")
        populate_technical_for_timeframe(conn, price_table, technical_table, timeframe)

    conn.close()
    logging.info("✅ Technical data population complete")

if __name__ == "__main__":
    main()
