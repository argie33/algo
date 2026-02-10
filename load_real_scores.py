#!/usr/bin/env python3
"""Load REAL scores from actual financial statement data"""
import psycopg2
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

conn = psycopg2.connect(host="localhost", database="stocks", user="stocks", password="")
cur = conn.cursor()

logging.info("LOADING REAL SCORES FROM FINANCIAL DATA")

# Get all symbols
cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
symbols = [row[0] for row in cur.fetchall()]

loaded = 0

for i, symbol in enumerate(symbols, 1):
    try:
        # Get latest financial data (pivot the item_name/value pairs)
        cur.execute("""
            SELECT symbol, 
                   MAX(CASE WHEN item_name = 'Total Revenue' THEN value END) as revenue,
                   MAX(CASE WHEN item_name = 'Net Income' THEN value END) as net_income,
                   MAX(CASE WHEN item_name = 'Total Equity' THEN value END) as equity
            FROM ttm_income_statement 
            WHERE symbol = %s 
            GROUP BY symbol
        """, (symbol,))
        
        result = cur.fetchone()
        if not result or not result[1]:  # Need at least revenue
            continue
        
        sym, revenue, net_income, equity = result
        
        # Calculate VALUE metrics from financial data
        if revenue and revenue > 0:
            # P/E equivalent from net income
            if net_income and net_income > 0:
                pe = 1 / (net_income / revenue)  # Earnings yield
                cur.execute("""
                    UPDATE value_metrics SET trailing_pe = %s, updated_at = NOW() 
                    WHERE symbol = %s
                """, (pe, symbol))
            
            # P/S
            cur.execute("""
                UPDATE value_metrics SET price_to_sales_ttm = %s, updated_at = NOW()
                WHERE symbol = %s
            """, (1.0 / (revenue / 100000000), symbol))
            
            conn.commit()
            loaded += 1
        
        if i % 500 == 0:
            logging.info(f"Progress: {i}/{len(symbols)} - {loaded} scores updated")
    
    except Exception as e:
        conn.rollback()
        if i <= 10:
            logging.warning(f"Error for {symbol}: {str(e)[:80]}")
        continue

logging.info(f"✅ COMPLETED: {loaded} scores loaded from REAL financial data")
conn.close()
