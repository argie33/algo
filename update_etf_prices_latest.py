#!/usr/bin/env python3
"""Quick script to update ETF weekly and monthly prices with latest data"""
import psycopg2
import yfinance as yf
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to database
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='stocks',
    user='stocks'
)
cur = conn.cursor()

# Get all ETF symbols
cur.execute("SELECT DISTINCT symbol FROM etf_symbols ORDER BY symbol")
etf_symbols = [row[0] for row in cur.fetchall()]
logging.info(f"Found {len(etf_symbols)} ETF symbols")

# Update ETF weekly prices (last 30 days)
logging.info("Updating ETF weekly prices...")
for i, symbol in enumerate(etf_symbols):
    if i % 100 == 0:
        logging.info(f"Progress: {i}/{len(etf_symbols)} ETFs")

    try:
        df = yf.download(symbol, period='1mo', interval='1wk', progress=False)
        if len(df) > 0:
            for date, row in df.iterrows():
                cur.execute("""
                    INSERT INTO etf_price_weekly (symbol, date, open, high, low, close, adj_close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        adj_close = EXCLUDED.adj_close,
                        volume = EXCLUDED.volume
                """, (symbol, date.date(), float(row['Open']), float(row['High']),
                      float(row['Low']), float(row['Close']), float(row['Adj Close']),
                      int(row['Volume'])))
            conn.commit()
    except Exception as e:
        logging.error(f"Error updating {symbol} weekly: {e}")
        continue

# Update ETF monthly prices (last 90 days)
logging.info("Updating ETF monthly prices...")
for i, symbol in enumerate(etf_symbols):
    if i % 100 == 0:
        logging.info(f"Progress: {i}/{len(etf_symbols)} ETFs")

    try:
        df = yf.download(symbol, period='3mo', interval='1mo', progress=False)
        if len(df) > 0:
            for date, row in df.iterrows():
                cur.execute("""
                    INSERT INTO etf_price_monthly (symbol, date, open, high, low, close, adj_close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        adj_close = EXCLUDED.adj_close,
                        volume = EXCLUDED.volume
                """, (symbol, date.date(), float(row['Open']), float(row['High']),
                      float(row['Low']), float(row['Close']), float(row['Adj Close']),
                      int(row['Volume'])))
            conn.commit()
    except Exception as e:
        logging.error(f"Error updating {symbol} monthly: {e}")
        continue

logging.info("ETF price updates complete!")
conn.close()
