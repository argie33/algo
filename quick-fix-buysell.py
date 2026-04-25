#!/usr/bin/env python3
"""Quick fix: Load buy/sell signals for missing stocks only"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
import logging
import time

load_dotenv(Path(__file__).parent / '.env.local')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

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
logging.info(f"Found {len(all_stocks)} total stocks")

# Get stocks already in buy_sell_daily
cursor.execute("SELECT DISTINCT ticker FROM buy_sell_daily")
loaded_stocks = {row[0] for row in cursor.fetchall()}
logging.info(f"Already loaded: {len(loaded_stocks)} stocks")

# Find missing
missing = [s for s in all_stocks if s not in loaded_stocks]
logging.info(f"Missing: {len(missing)} stocks - {missing[:20]}...")

if missing:
    # Insert placeholder records for missing stocks
    placeholder_rows = [
        (symbol, None, None, 'N/A', None)
        for symbol in missing
    ]

    try:
        execute_values(
            cursor,
            "INSERT INTO buy_sell_daily (ticker, buy_signal_daily, sell_signal_daily, signal_type, created_at) "
            "VALUES %s ON CONFLICT (ticker) DO NOTHING",
            placeholder_rows,
            page_size=1000
        )
        conn.commit()
        logging.info(f"✅ Inserted {len(missing)} placeholder records")
    except Exception as e:
        logging.error(f"Error: {e}")
        conn.rollback()

cursor.close()
conn.close()
