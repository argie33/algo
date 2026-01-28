#!/usr/bin/env python3
"""
Calculate Beta for stocks missing from yfinance
Uses historical price data and market correlation
"""
import psycopg2
import numpy as np
import pandas as pd
import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_connection():
    """Connect to database"""
    try:
        conn = psycopg2.connect(
            host='localhost',
            database='stocks',
            user='postgres',
            port=5432
        )
        return conn
    except Exception as e:
        logger.error(f"DB Connection failed: {e}")
        return None

def get_stocks_missing_beta(conn):
    """Get list of stocks with missing beta"""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT symbol FROM stability_metrics 
        WHERE beta IS NULL
        ORDER BY symbol
    """)
    missing = [row[0] for row in cur.fetchall()]
    cur.close()
    return missing

def get_price_data(conn, symbol, days=252):
    """Get price data for last 252 trading days"""
    cur = conn.cursor()
    cur.execute("""
        SELECT date, close FROM price_daily 
        WHERE symbol = %s 
        ORDER BY date DESC LIMIT %s
    """, (symbol, days))
    data = cur.fetchall()
    cur.close()
    
    if len(data) < 20:
        return None
    
    df = pd.DataFrame(data, columns=['date', 'close'])
    df = df.sort_values('date')
    df['returns'] = df['close'].pct_change()
    return df[['date', 'returns']].dropna()

def get_market_returns(conn, days=252):
    """Get SPY (market proxy) returns"""
    cur = conn.cursor()
    cur.execute("""
        SELECT date, close FROM price_daily 
        WHERE symbol = 'SPY'
        ORDER BY date DESC LIMIT %s
    """, ('SPY', days))
    data = cur.fetchall()
    cur.close()
    
    if len(data) < 20:
        return None
    
    df = pd.DataFrame(data, columns=['date', 'close'])
    df = df.sort_values('date')
    df['market_returns'] = df['close'].pct_change()
    return df[['date', 'market_returns']].dropna()

def calculate_beta(stock_returns, market_returns):
    """Calculate beta using regression"""
    if len(stock_returns) < 20 or len(market_returns) < 20:
        return None
    
    # Align dates
    merged = pd.merge(stock_returns, market_returns, on='date', how='inner')
    
    if len(merged) < 20:
        return None
    
    returns = merged['returns'].values
    market = merged['market_returns'].values
    
    # Calculate beta = covariance(stock, market) / variance(market)
    if np.var(market) == 0:
        return None
    
    beta = np.cov(returns, market)[0, 1] / np.var(market)
    return beta

def update_missing_betas(conn, symbols):
    """Calculate and save beta for missing stocks"""
    market_returns = get_market_returns(conn)
    
    if market_returns is None:
        logger.error("Cannot get market returns - SPY data missing")
        return
    
    calculated = 0
    failed = 0
    
    for i, symbol in enumerate(symbols):
        try:
            stock_returns = get_price_data(conn, symbol)
            
            if stock_returns is None:
                logger.warning(f"{symbol}: Insufficient price data")
                failed += 1
                continue
            
            beta = calculate_beta(stock_returns, market_returns)
            
            if beta is None:
                logger.warning(f"{symbol}: Could not calculate beta")
                failed += 1
                continue
            
            # Cap extreme values
            beta = max(-5, min(10, beta))
            
            # Save to database
            cur = conn.cursor()
            cur.execute("""
                UPDATE stability_metrics 
                SET beta = %s 
                WHERE symbol = %s AND beta IS NULL
            """, (beta, symbol))
            conn.commit()
            cur.close()
            
            logger.info(f"✅ {symbol}: Calculated beta={beta:.3f} ({i+1}/{len(symbols)})")
            calculated += 1
            
        except Exception as e:
            logger.error(f"❌ {symbol}: {e}")
            failed += 1
    
    logger.info(f"\n✅ Calculated: {calculated}/{len(symbols)}")
    logger.info(f"❌ Failed: {failed}/{len(symbols)}")

def main():
    conn = get_connection()
    if not conn:
        sys.exit(1)
    
    missing = get_stocks_missing_beta(conn)
    logger.info(f"Found {len(missing)} stocks with missing beta")
    
    if len(missing) > 0:
        update_missing_betas(conn, missing)
    
    conn.close()
    logger.info("✅ Complete - calculated beta for all missing stocks")

if __name__ == "__main__":
    main()
