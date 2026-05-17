#!/usr/bin/env python3
"""
Load technical indicators into technical_data_daily from price_daily.

Computes: RSI, MACD, SMA, EMA, ATR, Rate of Change, etc.
Uses watermarks — only inserts rows newer than the existing max date per symbol.
Warm-up: fetches 300 trading days of history before the watermark to seed indicators.
Run with --full-reload to clear and recompute everything.
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if not env_file.exists():
    env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

WARMUP_DAYS = 300  # history needed to warm up 200-day SMA


def _get_db_config():
    from config.credential_helper import get_db_password
    return dict(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )


def calculate_rsi(prices, period=14):
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period + 1:
        return np.full(len(prices), 50.0)
    deltas = np.diff(prices)
    seed = deltas[:period + 1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rsi = np.full(len(prices), 50.0)
    rs = np.zeros(len(prices))
    if down != 0:
        rsi[:period] = 100.0 - 100.0 / (1.0 + up / down)
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        upval = max(delta, 0.0)
        downval = max(-delta, 0.0)
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs[i] = up / down if down != 0 else rs[i - 1]
        rsi[i] = 100.0 - 100.0 / (1.0 + rs[i])
    return rsi


def calculate_sma(prices, period):
    return pd.Series(np.asarray(prices, dtype=float)).rolling(window=period, min_periods=1).mean().values


def calculate_ema(prices, period):
    return pd.Series(np.asarray(prices, dtype=float)).ewm(span=period, min_periods=1, adjust=False).mean().values


def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = np.asarray(calculate_ema(prices, fast), dtype=float)
    ema_slow = np.asarray(calculate_ema(prices, slow), dtype=float)
    macd_line = ema_fast - ema_slow
    signal_line = np.asarray(calculate_ema(macd_line, signal), dtype=float)
    return macd_line, signal_line, macd_line - signal_line


def calculate_atr(high, low, close, period=14):
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)
    tr = np.empty(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return pd.Series(tr).rolling(window=period, min_periods=1).mean().values


def calculate_roc(prices, period):
    prices = np.asarray(prices, dtype=float)
    roc = np.zeros(len(prices))
    for i in range(period, len(prices)):
        if prices[i - period] != 0:
            roc[i] = ((prices[i] - prices[i - period]) / prices[i - period]) * 100
    return roc


def process_symbol(symbol, watermark, conn_params):
    """Compute and insert technical indicators for one symbol."""
    try:
        conn = psycopg2.connect(**conn_params)
        cur = conn.cursor()

        start_date = (watermark - timedelta(days=int(WARMUP_DAYS * 1.5))) if watermark else date(2000, 1, 1)

        cur.execute("""
            SELECT date, high, low, close
            FROM price_daily
            WHERE symbol = %s AND date >= %s
            ORDER BY date ASC
        """, (symbol, start_date))
        rows = cur.fetchall()

        if not rows or len(rows) < 2:
            conn.close()
            return symbol, 0, None

        dates = [r[0] for r in rows]
        highs = np.array([float(r[1]) for r in rows])
        lows = np.array([float(r[2]) for r in rows])
        closes = np.array([float(r[3]) for r in rows])

        rsi_vals = calculate_rsi(closes)
        sma20 = calculate_sma(closes, 20)
        sma50 = calculate_sma(closes, 50)
        sma200 = calculate_sma(closes, 200)
        ema12 = calculate_ema(closes, 12)
        ema26 = calculate_ema(closes, 26)
        macd, macd_sig, macd_hist = calculate_macd(closes)
        atr_vals = calculate_atr(highs, lows, closes)
        mom = np.concatenate([[0.0], np.diff(closes)]) * 100
        roc10 = calculate_roc(closes, 10)
        roc20 = calculate_roc(closes, 20)
        roc60 = calculate_roc(closes, 60)
        roc120 = calculate_roc(closes, 120)
        roc252 = calculate_roc(closes, 252)

        rows_to_insert = []
        for i, d in enumerate(dates):
            if watermark and d <= watermark:
                continue
            rows_to_insert.append((
                symbol, d,
                float(rsi_vals[i]), float(macd[i]), float(macd_sig[i]), float(macd_hist[i]),
                float(mom[i]),
                float(roc10[i]), float(roc10[i]), float(roc20[i]),
                float(roc60[i]), float(roc120[i]), float(roc252[i]),
                float(sma20[i]), float(sma50[i]), float(sma200[i]),
                float(ema12[i]), float(ema26[i]), float(atr_vals[i]),
                0.0, 0.0, 0.0, 0.0,  # adx, plus_di, minus_di, mansfield_rs
            ))

        if rows_to_insert:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO technical_data_daily
                (symbol, date, rsi, macd, macd_signal, macd_hist, mom,
                 roc, roc_10d, roc_20d, roc_60d, roc_120d, roc_252d,
                 sma_20, sma_50, sma_200, ema_12, ema_26, atr,
                 adx, plus_di, minus_di, mansfield_rs, created_at)
                VALUES %s
                ON CONFLICT (symbol, date) DO UPDATE SET
                  rsi=EXCLUDED.rsi, macd=EXCLUDED.macd, macd_signal=EXCLUDED.macd_signal,
                  macd_hist=EXCLUDED.macd_hist, mom=EXCLUDED.mom,
                  roc=EXCLUDED.roc, roc_10d=EXCLUDED.roc_10d, roc_20d=EXCLUDED.roc_20d,
                  roc_60d=EXCLUDED.roc_60d, roc_120d=EXCLUDED.roc_120d, roc_252d=EXCLUDED.roc_252d,
                  sma_20=EXCLUDED.sma_20, sma_50=EXCLUDED.sma_50, sma_200=EXCLUDED.sma_200,
                  ema_12=EXCLUDED.ema_12, ema_26=EXCLUDED.ema_26, atr=EXCLUDED.atr
            """, rows_to_insert,
                template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())")
            conn.commit()

        conn.close()
        return symbol, len(rows_to_insert), None

    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return symbol, 0, str(e)


def load_technical_indicators(symbols=None, parallelism=8):
    conn_params = _get_db_config()
    conn = psycopg2.connect(**conn_params)
    cur = conn.cursor()

    if symbols is None:
        cur.execute("SELECT DISTINCT symbol FROM price_daily ORDER BY symbol")
        symbols = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT symbol, MAX(date) FROM technical_data_daily
        WHERE symbol = ANY(%s)
        GROUP BY symbol
    """, (symbols,))
    watermarks = {r[0]: r[1] for r in cur.fetchall()}
    cur.close()
    conn.close()

    total = len(symbols)
    inserted = 0
    errors = 0
    skipped = 0

    logger.info(f"Technical indicators: {total} symbols (parallelism={parallelism})")

    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        futures = {executor.submit(process_symbol, sym, watermarks.get(sym), conn_params): sym for sym in symbols}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            sym, count, err = future.result()
            if err:
                errors += 1
                logger.debug(f"  ERROR {sym}: {err}")
            elif count == 0:
                skipped += 1
            else:
                inserted += count

            if completed % 200 == 0:
                logger.info(f"  {completed}/{total} processed ({inserted} rows inserted, {errors} errors)")

    logger.info(f"Completed: {total} symbols, {inserted} new rows, {errors} errors, {skipped} up-to-date")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbols', help='Comma-separated symbols (default: all)')
    parser.add_argument('--parallelism', type=int, default=8)
    parser.add_argument('--full-reload', action='store_true', help='Clear and recompute from scratch')
    args = parser.parse_args()

    if args.full_reload:
        conn = psycopg2.connect(**_get_db_config())
        cur = conn.cursor()
        cur.execute("DELETE FROM technical_data_daily")
        conn.commit()
        conn.close()
        logger.info("Cleared technical_data_daily for full reload")

    syms = [s.strip().upper() for s in args.symbols.split(',')] if args.symbols else None
    load_technical_indicators(symbols=syms, parallelism=args.parallelism)
