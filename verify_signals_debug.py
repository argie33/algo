#!/usr/bin/env python3
"""
Signal Verification Debug Script
Compares database signals with TradingView Pine Script logic

Usage: python3 verify_signals_debug.py TSLY
"""

import sys
import os
import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv('/home/stocks/algo/.env.local')

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "password")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "stocks")

def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        options='-c statement_timeout=30000'
    )
    return conn

def fetch_price_data(symbol, months_back=12):
    """Fetch price data for debugging"""
    conn = get_db_connection()
    cur = conn.cursor()

    start_date = datetime.now() - timedelta(days=30*months_back)

    sql = """
        SELECT date, open, high, low, close, volume
        FROM price_daily
        WHERE symbol = %s AND date >= %s
        ORDER BY date ASC
    """

    cur.execute(sql, (symbol, start_date.date()))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.reset_index(drop=True)

def fetch_database_signals(symbol):
    """Fetch signals from database"""
    conn = get_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT date, signal, buylevel, stoplevel, sma_50
        FROM buy_sell_daily
        WHERE symbol = %s AND signal IN ('Buy', 'Sell')
        ORDER BY date ASC
    """

    cur.execute(sql, (symbol,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=['date', 'signal', 'buylevel', 'stoplevel', 'sma_50'])
    df['date'] = pd.to_datetime(df['date'])
    return df.reset_index(drop=True)

def calculate_sma(prices, period):
    """Calculate Simple Moving Average"""
    return prices.rolling(window=period).mean()

def detect_pivot_highs_simple(highs, left=3, right=3):
    """Detect pivot highs - EXACT Pine Script matching"""
    pivots = [None] * len(highs)

    for i in range(left, len(highs) - right):
        is_pivot = True

        # Check left side - all bars to left must be strictly lower
        for j in range(left):
            if highs.iloc[i - left + j] >= highs.iloc[i]:
                is_pivot = False
                break

        # Check right side - all bars to right must be strictly lower
        if is_pivot:
            for j in range(right):
                if highs.iloc[i + j + 1] >= highs.iloc[i]:
                    is_pivot = False
                    break

        if is_pivot:
            # Mark at position i (the pivot itself)
            pivots[i] = highs.iloc[i]

    return pd.Series(pivots, index=highs.index)

def detect_pivot_lows_simple(lows, left=3, right=3):
    """Detect pivot lows - EXACT Pine Script matching"""
    pivots = [None] * len(lows)

    for i in range(left, len(lows) - right):
        is_pivot = True

        # Check left side - all bars to left must be strictly higher
        for j in range(left):
            if lows.iloc[i - left + j] <= lows.iloc[i]:
                is_pivot = False
                break

        # Check right side - all bars to right must be strictly higher
        if is_pivot:
            for j in range(right):
                if lows.iloc[i + j + 1] <= lows.iloc[i]:
                    is_pivot = False
                    break

        if is_pivot:
            # Mark at position i (the pivot itself)
            pivots[i] = lows.iloc[i]

    return pd.Series(pivots, index=lows.index)

def generate_signals_debug(df):
    """Generate signals - EXACT matching Pine Script"""

    # Calculate technical indicators
    df['sma_50'] = calculate_sma(df['close'], 50)
    df['sma_200'] = calculate_sma(df['close'], 200)

    # Detect pivots
    pivot_highs = detect_pivot_highs_simple(df['high'])
    pivot_lows = detect_pivot_lows_simple(df['low'])

    # Forward fill levels
    df['buyLevel'] = pivot_highs.ffill()
    df['stopLevel'] = pivot_lows.ffill()
    df['maFilter'] = df['sma_50'].ffill()

    # Generate buy/sell signals matching Pine Script
    df['buySignal'] = (df['high'] > df['buyLevel']) & df['buyLevel'].notna()
    df['sellSignal'] = (df['low'] < df['stopLevel']) & df['stopLevel'].notna()
    df['aboveMA'] = (df['buyLevel'] > df['maFilter']) | df['maFilter'].isna()

    # State machine
    signals = []
    in_pos = False

    for i in range(len(df)):
        buy_cond = df.iloc[i]['buySignal'] and df.iloc[i]['aboveMA']
        sell_cond = df.iloc[i]['sellSignal']

        if i > 0:
            if signals[i-1] == 'Buy':
                in_pos = True
            elif signals[i-1] == 'Sell':
                in_pos = False

        flat = not in_pos

        if buy_cond and flat:
            signals.append('Buy')
        elif sell_cond and in_pos:
            signals.append('Sell')
        else:
            signals.append('None')

    df['Signal'] = signals
    return df

def debug_symbol(symbol):
    """Debug signals for a symbol"""
    print(f"\n{'='*80}")
    print(f"DEBUGGING SIGNALS FOR {symbol}")
    print(f"{'='*80}")

    # Fetch price data
    print(f"\n1. Fetching price data for {symbol}...")
    price_df = fetch_price_data(symbol, months_back=12)

    if price_df.empty:
        print(f"   ERROR: No price data found for {symbol}")
        return

    print(f"   ✅ Found {len(price_df)} price bars (from {price_df['date'].min().date()} to {price_df['date'].max().date()})")

    # Fetch database signals
    print(f"\n2. Fetching signals from database...")
    db_signals = fetch_database_signals(symbol)

    if db_signals.empty:
        print(f"   No signals found in database")
    else:
        print(f"   ✅ Found {len(db_signals)} signals in database:")
        for _, row in db_signals.iterrows():
            print(f"      {row['date'].date()}: {row['signal']:5} (BuyLevel: {row['buylevel']:.2f}, StopLevel: {row['stoplevel']:.2f})")

    # Generate signals using Pine Script logic
    print(f"\n3. Regenerating signals using Pine Script logic...")
    calc_df = generate_signals_debug(price_df.copy())

    calc_signals = calc_df[calc_df['Signal'] != 'None'].copy()
    print(f"   ✅ Generated {len(calc_signals)} signals:")
    for _, row in calc_signals.iterrows():
        print(f"      {row['date'].date()}: {row['Signal']:5} (BuyLevel: {row['buyLevel']:.2f}, StopLevel: {row['stopLevel']:.2f})")

    # Compare
    print(f"\n4. COMPARISON:")
    print(f"   Database signals: {len(db_signals)}")
    print(f"   Calculated signals: {len(calc_signals)}")

    if len(calc_signals) > 0:
        # Find signals that are in database but not in calculation
        db_dates = set(db_signals['date'].dt.date)
        calc_dates = set(calc_signals['date'].dt.date)

        extra_in_db = db_dates - calc_dates
        extra_in_calc = calc_dates - db_dates

        if extra_in_db:
            print(f"\n   ⚠️  EXTRA signals in database (not in calculation):")
            for date in sorted(extra_in_db):
                row = db_signals[db_signals['date'].dt.date == date].iloc[0]
                print(f"      {date}: {row['signal']} ← SPURIOUS!")

        if extra_in_calc:
            print(f"\n   ⚠️  EXTRA signals in calculation (not in database):")
            for date in sorted(extra_in_calc):
                row = calc_signals[calc_signals['date'].dt.date == date].iloc[0]
                print(f"      {date}: {row['Signal']} ← MISSING!")

    # Show recent 20 bars for manual inspection
    print(f"\n5. RECENT PRICE ACTION (last 20 bars):")
    recent = price_df.tail(20).copy()
    recent = generate_signals_debug(recent.copy())

    print(f"\n   {'Date':<12} {'High':<8} {'Low':<8} {'Close':<8} {'Signal':<6} {'BuyLvl':<8} {'StopLvl':<8} {'SMA50':<8}")
    print(f"   {'-'*80}")

    for _, row in recent.iterrows():
        print(f"   {row['date'].date()} {row['high']:7.2f} {row['low']:7.2f} {row['close']:7.2f} {row['Signal']:<6} {row['buyLevel']:.2f} {row['stopLevel']:.2f} {row['sma_50']:.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} SYMBOL")
        print(f"Example: python3 {sys.argv[0]} TSLY")
        sys.exit(1)

    symbol = sys.argv[1].upper()
    debug_symbol(symbol)
