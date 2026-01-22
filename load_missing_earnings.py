#!/usr/bin/env python3
"""
Load missing earnings revisions for stocks that failed on first attempt
"""
import os
import sys
import logging
import time
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DB_HOST = "localhost"
DB_PORT = "5432"
DB_USER = "stocks"
DB_PASSWORD = "bed0elAn"
DB_NAME = "stocks"

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME)

def load_missing_stocks():
    """Load earnings data for missing stocks"""
    conn = get_db_connection()
    today = datetime.now().date()
    
    try:
        # Get missing stocks
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol FROM stock_symbols 
                WHERE symbol IS NOT NULL AND etf = 'N'
                AND symbol NOT IN (SELECT DISTINCT symbol FROM earnings_estimate_revisions)
                ORDER BY symbol
            """)
            missing_symbols = [row[0] for row in cur.fetchall()]
        
        logger.info(f"🎯 Loading {len(missing_symbols)} missing stocks...")
        
        trends_data = []
        revisions_data = []
        success_count = 0
        
        for idx, symbol in enumerate(missing_symbols, 1):
            if idx % 100 == 0:
                logger.info(f"Progress: {idx}/{len(missing_symbols)}")
            
            for attempt in range(3):
                try:
                    ticker = yf.Ticker(symbol)
                    
                    eps_trend = ticker.eps_trend
                    if eps_trend is not None and not eps_trend.empty:
                        for period in eps_trend.index:
                            row = eps_trend.loc[period]
                            trends_data.append((
                                symbol, str(period), today,
                                float(row.get('current')) if row.get('current') is not None else None,
                                float(row.get('7daysAgo')) if row.get('7daysAgo') is not None else None,
                                float(row.get('30daysAgo')) if row.get('30daysAgo') is not None else None,
                                float(row.get('60daysAgo')) if row.get('60daysAgo') is not None else None,
                                float(row.get('90daysAgo')) if row.get('90daysAgo') is not None else None
                            ))
                    
                    eps_revisions = ticker.eps_revisions
                    if eps_revisions is not None and not eps_revisions.empty:
                        for period in eps_revisions.index:
                            row = eps_revisions.loc[period]
                            revisions_data.append((
                                symbol, str(period), today,
                                int(row.get('upLast7days', 0)),
                                int(row.get('upLast30days', 0)),
                                int(row.get('downLast7Days', 0)),
                                int(row.get('downLast30days', 0))
                            ))
                    
                    if (eps_trend is not None and not eps_trend.empty) or (eps_revisions is not None and not eps_revisions.empty):
                        success_count += 1
                    
                    break
                    
                except Exception as e:
                    if attempt == 2:
                        pass
                    else:
                        time.sleep(0.5 * (attempt + 1))
                    continue
            
            time.sleep(0.3)
        
        # Deduplicate before insert
        trends_data = list(set(trends_data))
        revisions_data = list(set(revisions_data))
        
        logger.info(f"\n💾 Inserting {len(trends_data)} trend + {len(revisions_data)} revision records...")
        
        if trends_data:
            with conn.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO earnings_estimate_trends
                    (symbol, period, snapshot_date, current_estimate, estimate_7d_ago, estimate_30d_ago, estimate_60d_ago, estimate_90d_ago)
                    VALUES %s
                    ON CONFLICT (symbol, period, snapshot_date) DO NOTHING
                """, trends_data, page_size=100)
                conn.commit()
                logger.info(f"✅ Inserted {len(trends_data)} trend records")
        
        if revisions_data:
            with conn.cursor() as cur:
                execute_values(cur, """
                    INSERT INTO earnings_estimate_revisions
                    (symbol, period, snapshot_date, up_last_7d, up_last_30d, down_last_7d, down_last_30d)
                    VALUES %s
                    ON CONFLICT (symbol, period, snapshot_date) DO NOTHING
                """, revisions_data, page_size=100)
                conn.commit()
                logger.info(f"✅ Inserted {len(revisions_data)} revision records")
        
        logger.info(f"\n📊 Successfully loaded: {success_count}/{len(missing_symbols)}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    load_missing_stocks()
    logger.info("✅ Done!")
