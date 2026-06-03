#!/usr/bin/env python3
"""Check recent trades to understand what's happening."""
import psycopg2
import os
from datetime import datetime

db_host = os.getenv('DB_HOST', 'localhost')
db_user = os.getenv('DB_USER', 'postgres')
db_password = os.getenv('DB_PASSWORD', '')
db_name = os.getenv('DB_NAME', 'stocks')

try:
    conn = psycopg2.connect(
        host=db_host,
        user=db_user,
        password=db_password if db_password else None,
        database=db_name
    )
    cur = conn.cursor()

    print("=== ALL TRADES (Last 20) ===")
    cur.execute("""
        SELECT entry_time::date, symbol, entry_price, exit_price, status, entry_time
        FROM algo_trades
        ORDER BY algo_trades.entry_time DESC
        LIMIT 20
    """)
    for row in cur.fetchall():
        date_col, symbol, entry, exit_p, status, full_time = row
        exit_str = f"{exit_p:.2f}" if exit_p else "None"
        print(f"{date_col} | {symbol:6s} | Entry: {entry:7.2f} | Exit: {exit_str:7s} | Status: {status:10s} | Time: {full_time}")

    print("\n=== POSITIONS (Open) ===")
    cur.execute("""
        SELECT symbol, quantity, entry_price, current_price, opened_at
        FROM algo_positions
        WHERE closed_at IS NULL
        ORDER BY opened_at DESC
    """)
    rows = cur.fetchall()
    print(f"Total open: {len(rows)}")
    for symbol, qty, entry, current, opened in rows:
        current_str = f"{current:.2f}" if current else "None"
        print(f"  {symbol:6s} | Qty: {qty:3d} | Entry: {entry:7.2f} | Current: {current_str:7s} | Opened: {opened}")

    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
