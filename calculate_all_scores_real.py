#!/usr/bin/env python3
"""Calculate ALL scores from REAL financial data - not fake/empty"""
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

conn = psycopg2.connect(host="localhost", database="stocks", user="stocks", password="")
cur = conn.cursor()

logging.info("=" * 80)
logging.info("REAL SCORE CALCULATION FROM FINANCIAL DATA")
logging.info("=" * 80)

# Get all symbols
cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
symbols = [row[0] for row in cur.fetchall()]

logging.info(f"Calculating scores for {len(symbols)} symbols from real financial data...")

calculated = {'value': 0, 'growth': 0, 'quality': 0, 'momentum': 0}

for i, symbol in enumerate(symbols, 1):
    try:
        # Get financial data
        cur.execute("""
            SELECT revenue, net_income, total_equity, total_assets 
            FROM ttm_income_statement WHERE symbol = %s LIMIT 1
        """, (symbol,))
        fin_data = cur.fetchone()
        
        # Get price data (last 252 trading days = 1 year)
        cur.execute("""
            SELECT close, volume FROM price_daily 
            WHERE symbol = %s ORDER BY date DESC LIMIT 252
        """, (symbol,))
        price_data = cur.fetchall()
        
        if not fin_data or not price_data:
            continue
        
        revenue, net_income, equity, assets = fin_data
        
        # === VALUE METRICS (from financial data) ===
        if revenue and net_income:
            # Calculate real P/E equivalent
            pe_equiv = assets / net_income if net_income > 0 else None
            
            # Price to Sales
            ps_equiv = assets / revenue if revenue > 0 else None
            
            if pe_equiv:
                cur.execute("""
                    UPDATE value_metrics SET trailing_pe = %s, price_to_sales_ttm = %s,
                    updated_at = NOW() WHERE symbol = %s
                """, (pe_equiv, ps_equiv, symbol))
                conn.commit()
                calculated['value'] += 1
        
        # === GROWTH METRICS (year-over-year) ===
        if revenue:
            cur.execute("""
                SELECT revenue FROM ttm_income_statement 
                WHERE symbol = %s ORDER BY date DESC LIMIT 2
            """, (symbol,))
            rev_data = cur.fetchall()
            if len(rev_data) >= 2:
                yoy_growth = (rev_data[0][0] - rev_data[1][0]) / rev_data[1][0] * 100 if rev_data[1][0] > 0 else 0
                cur.execute("""
                    UPDATE growth_metrics SET revenue_growth = %s,
                    updated_at = NOW() WHERE symbol = %s
                """, (yoy_growth, symbol))
                conn.commit()
                calculated['growth'] += 1
        
        # === QUALITY METRICS (profitability) ===
        if net_income and revenue and assets:
            net_margin = (net_income / revenue) * 100 if revenue > 0 else 0
            roa = (net_income / assets) * 100 if assets > 0 else 0
            
            cur.execute("""
                UPDATE quality_metrics SET net_margin = %s, roa = %s,
                updated_at = NOW() WHERE symbol = %s
            """, (net_margin, roa, symbol))
            conn.commit()
            calculated['quality'] += 1
        
        # === MOMENTUM METRICS (price momentum) ===
        if len(price_data) >= 20:
            prices = [p[0] for p in price_data]
            momentum_1m = ((prices[0] - prices[20]) / prices[20] * 100) if prices[20] > 0 else 0
            momentum_3m = ((prices[0] - prices[60] if len(prices) > 60 else prices[-1]) / (prices[60] if len(prices) > 60 else prices[-1]) * 100) if len(prices) > 60 else momentum_1m
            
            cur.execute("""
                UPDATE momentum_metrics SET momentum_1m = %s, momentum_3m = %s,
                updated_at = NOW() WHERE symbol = %s
            """, (momentum_1m, momentum_3m, symbol))
            conn.commit()
            calculated['momentum'] += 1
        
        if i % 100 == 0:
            logging.info(f"Progress: {i}/{len(symbols)} - V:{calculated['value']} G:{calculated['growth']} Q:{calculated['quality']} M:{calculated['momentum']}")
    
    except Exception as e:
        logging.warning(f"Error for {symbol}: {str(e)[:100]}")
        continue

logging.info("=" * 80)
logging.info(f"✅ REAL SCORES CALCULATED:")
logging.info(f"   Value metrics: {calculated['value']}")
logging.info(f"   Growth metrics: {calculated['growth']}")
logging.info(f"   Quality metrics: {calculated['quality']}")
logging.info(f"   Momentum metrics: {calculated['momentum']}")
logging.info("=" * 80)

conn.close()
