#!/usr/bin/env python3
"""
Validate all signals in the database against Pine Script logic
Find symbols with mismatched signals
"""

import psycopg2
import os
import pandas as pd
import numpy as np
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

def check_signal_consistency():
    """Check if signals are consistent within themselves"""
    conn = get_db_connection()
    cur = conn.cursor()

    print("SIGNAL CONSISTENCY CHECK")
    print("=" * 80)

    # Get all symbols that have Buy/Sell signals
    cur.execute("""
        SELECT symbol, COUNT(*) as signal_count,
               MIN(date) as first_signal,
               MAX(date) as last_signal
        FROM buy_sell_daily
        WHERE signal IN ('Buy', 'Sell')
        GROUP BY symbol
        ORDER BY last_signal DESC
        LIMIT 100
    """)

    symbols = cur.fetchall()

    print(f"\nFound {len(symbols)} symbols with Buy/Sell signals")
    print(f"\n{'Symbol':<10} {'Signals':<8} {'First':<12} {'Last':<12}")
    print("-" * 50)

    for symbol, count, first, last in symbols:
        print(f"{symbol:<10} {count:<8} {first} {last}")

        # Check signal sequence for each symbol
        cur.execute("""
            SELECT date, signal
            FROM buy_sell_daily
            WHERE symbol = %s AND signal IN ('Buy', 'Sell')
            ORDER BY date
        """, (symbol,))

        signals = cur.fetchall()

        # Check if alternating (Buy, Sell, Buy, Sell...)
        prev_signal = None
        has_duplicate = False

        for date, signal in signals:
            if prev_signal == signal:
                print(f"  ⚠️  DUPLICATE {signal} on {date} (previous {date})")
                has_duplicate = True
            prev_signal = signal

        if has_duplicate:
            print(f"  {symbol}: HAS SIGNAL DUPLICATES - Invalid state machine!")

    cur.close()
    conn.close()

if __name__ == "__main__":
    check_signal_consistency()
