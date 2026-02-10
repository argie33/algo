#!/usr/bin/env python3
"""Calculate A/D Rating from price_daily volume/price data"""
import psycopg2
import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

conn = psycopg2.connect(host="localhost", database="stocks", user="stocks", password="")
cur = conn.cursor()

# Get all symbols
cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
symbols = [row[0] for row in cur.fetchall()]

logging.info(f"Calculating A/D Rating for {len(symbols)} symbols")

calculated = 0
for i, symbol in enumerate(symbols, 1):
    try:
        # Get 13 weeks of price data
        cur.execute("""
            SELECT date, close, volume FROM price_daily 
            WHERE symbol = %s AND date >= NOW() - INTERVAL '13 weeks'
            ORDER BY date
        """, (symbol,))
        
        data = cur.fetchall()
        if len(data) < 5:  # Need minimum data
            continue
        
        # Calculate A/D Line (simple version: cumulative volume * price direction)
        ad_line = 0
        for i in range(1, len(data)):
            prev_close = data[i-1][1]
            curr_close = data[i][1]
            volume = data[i][2]
            
            if curr_close > prev_close:
                ad_line += volume
            elif curr_close < prev_close:
                ad_line -= volume
        
        # Calculate A/D Rating (0-100 scale)
        if len(data) > 0:
            ad_rating = min(100, max(0, 50 + (ad_line / (sum(v[2] for v in data)) * 50)))
        else:
            ad_rating = None
        
        if ad_rating is not None:
            cur.execute("""
                UPDATE positioning_metrics 
                SET ad_rating = %s, updated_at = NOW()
                WHERE symbol = %s
            """, (ad_rating, symbol))
            conn.commit()
            calculated += 1
            
            if i % 100 == 0:
                logging.info(f"Progress: {i}/{len(symbols)} - {calculated} ratings calculated")
    
    except Exception as e:
        logging.warning(f"Error for {symbol}: {e}")
        continue

logging.info(f"✅ Calculated A/D Rating for {calculated} symbols")
conn.close()
