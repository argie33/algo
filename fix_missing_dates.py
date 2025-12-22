#!/usr/bin/env python3
"""Fix missing dates in price_daily table"""
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv

load_dotenv('/home/stocks/algo/.env.local')

# DB config
conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "stocks"),
    password=os.environ.get("DB_PASSWORD", "bed0elAn"),
    dbname=os.environ.get("DB_NAME", "stocks")
)
cur = conn.cursor()

# Get symbols with gaps - those with Dec 11 but missing Dec 12
cur.execute("""
SELECT DISTINCT pd.symbol 
FROM price_daily pd
WHERE pd.date = '2025-12-11'
AND NOT EXISTS (SELECT 1 FROM price_daily WHERE symbol = pd.symbol AND date = '2025-12-12')
ORDER BY pd.symbol
""")

symbols_with_gaps = [row[0] for row in cur.fetchall()]
print(f"Found {len(symbols_with_gaps)} symbols with missing Dec 12 data")

# Download and insert Dec 12 data
inserted = 0
failed = 0
for i, symbol in enumerate(symbols_with_gaps):
    try:
        df = yf.download(symbol, start='2025-12-12', end='2025-12-12', progress=False)
        if df.empty or df.isnull().all().all():
            failed += 1
            continue
        
        # Handle both Series and DataFrame
        if isinstance(df, pd.Series):
            df = df.to_frame().T
        
        # Normalize columns to lowercase
        df.columns = [str(col).lower() for col in df.columns]
        
        # Extract values
        row_data = df.iloc[0]
        date = df.index[0].date()
        
        # Insert
        execute_values(cur,
            "INSERT INTO price_daily (symbol, date, open, high, low, close, adj_close, volume, dividends, stock_splits) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (symbol, date) DO NOTHING",
            [[symbol, date, 
              float(row_data.get('open')), float(row_data.get('high')), 
              float(row_data.get('low')), float(row_data.get('close')), 
              float(row_data.get('adj close', row_data.get('adj_close', row_data.get('close')))),
              int(row_data.get('volume', 0)), 
              float(row_data.get('dividends', 0)), float(row_data.get('stock_splits', 0))
            ]]
        )
        conn.commit()
        inserted += 1
        
        if i % 100 == 0:
            print(f"  {i}/{len(symbols_with_gaps)}: {symbol} ✅")
    except Exception as e:
        failed += 1
        if i < 5:  # Show first 5 errors
            print(f"  {symbol}: {str(e)[:80]}")

print(f"\n✅ Inserted: {inserted}")
print(f"❌ Failed: {failed}")

# Verify DKNG
cur.execute("SELECT date FROM price_daily WHERE symbol='DKNG' AND date BETWEEN '2025-12-08' AND '2025-12-19' ORDER BY date")
print(f"\nDKNG dates in DB:")
for row in cur.fetchall():
    print(f"  {row[0]}")

conn.close()
