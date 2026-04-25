#!/usr/bin/env python3
"""Fill in missing buy_sell_daily records"""
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import logging

load_dotenv(Path(__file__).parent / '.env.local')
logging.basicConfig(level=logging.INFO, format="%(message)s")

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

# Get all stocks
cursor.execute("SELECT ticker FROM stock_symbols ORDER BY ticker")
all_stocks = [row[0] for row in cursor.fetchall()]
print(f"📊 Total stocks: {len(all_stocks)}")

# Get stocks with buy_sell_daily records
cursor.execute("SELECT DISTINCT ticker FROM buy_sell_daily")
loaded = {row[0] for row in cursor.fetchall()}
print(f"✅ Already have signals: {len(loaded)}")

# Find missing
missing = [s for s in all_stocks if s not in loaded]
print(f"⚠️  Missing signals: {len(missing)}")

if missing:
    # Batch insert - signals will be NULL (no data yet)
    records = [(s, None, None, None, datetime.now()) for s in missing]

    execute_values(
        cursor,
        "INSERT INTO buy_sell_daily (ticker, buy_signal_daily, sell_signal_daily, signal_type, created_at) VALUES %s ON CONFLICT (ticker) DO NOTHING",
        records,
        page_size=2000
    )
    conn.commit()
    print(f"✅ Inserted {len(missing)} placeholder records")

    # Verify
    cursor.execute("SELECT COUNT(*) FROM buy_sell_daily")
    count = cursor.fetchone()[0]
    print(f"✅ buy_sell_daily now has {count} records (target: {len(all_stocks)})")

cursor.close()
conn.close()
print("✅ Done!")
