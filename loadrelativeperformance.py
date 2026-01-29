#!/usr/bin/env python3
"""
Relative Performance Metrics Loader
Calculates: Alpha, Tracking Error, Active Return, Information Ratio, Relative Volatility
Using 252 trading days (1 year) of price data vs SPY
"""
import sys
import logging
import json
import os
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

SCRIPT_NAME = "loadrelativeperformance.py"
TRADING_DAYS = 252  # 1 year of trading data
RISK_FREE_RATE = 0.045  # 4.5% annual risk-free rate

def get_db_config():
    """Get database configuration from environment or AWS Secrets Manager"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception as e:
        logging.debug(f"AWS Secrets Manager not available, using local config: {e}")
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def calculate_relative_metrics(stock_prices, spy_prices):
    """
    Calculate relative performance metrics
    Returns: alpha, tracking_error, active_return, info_ratio, rel_volatility
    """
    try:
        if len(stock_prices) < 30 or len(spy_prices) < 30:
            return None, None, None, None, None
        
        # Calculate daily returns
        stock_returns = stock_prices.pct_change().dropna()
        spy_returns = spy_prices.pct_change().dropna()
        
        if len(stock_returns) < 30 or len(spy_returns) < 30:
            return None, None, None, None, None
        
        # Align the data
        common_dates = stock_returns.index.intersection(spy_returns.index)
        if len(common_dates) < 30:
            return None, None, None, None, None
        
        stock_ret = stock_returns[common_dates]
        spy_ret = spy_returns[common_dates]
        
        # Annual metrics
        stock_annual_return = (1 + stock_ret.mean()) ** 252 - 1
        spy_annual_return = (1 + spy_ret.mean()) ** 252 - 1
        
        stock_volatility = stock_ret.std() * np.sqrt(252)
        spy_volatility = spy_ret.std() * np.sqrt(252)
        
        # Active return (annualized)
        active_return = stock_annual_return - spy_annual_return
        
        # Tracking error (annualized std of excess returns)
        excess_returns = stock_ret - spy_ret
        tracking_error = excess_returns.std() * np.sqrt(252)
        
        # Information ratio
        info_ratio = active_return / tracking_error if tracking_error > 0 else None
        
        # Relative volatility
        rel_volatility = stock_volatility / spy_volatility if spy_volatility > 0 else None
        
        # Alpha (requires beta, which we should get from positioning_metrics)
        # Using CAPM: Alpha = Return - (Risk-free + Beta × (Market Return - Risk-free))
        # For now, we'll calculate the residual alpha
        covariance = np.cov(stock_ret, spy_ret)[0, 1]
        spy_variance = np.var(spy_ret)
        beta = covariance / spy_variance if spy_variance > 0 else None
        
        if beta:
            alpha = stock_annual_return - (RISK_FREE_RATE + beta * (spy_annual_return - RISK_FREE_RATE))
        else:
            alpha = None
        
        return alpha, tracking_error, active_return, info_ratio, rel_volatility
        
    except Exception as e:
        logging.warning(f"Error calculating metrics: {e}")
        return None, None, None, None, None

def load_relative_performance(symbols, cur, conn):
    """Load relative performance metrics for all symbols"""
    total = len(symbols)
    logging.info(f"Calculating relative performance for {total} symbols")
    processed, failed = 0, []
    
    # Get SPY data
    logging.info("Loading SPY price data...")
    cur.execute("""
        SELECT date, close FROM price_daily 
        WHERE symbol = 'SPY' 
        ORDER BY date DESC 
        LIMIT 252
    """)
    spy_data = cur.fetchall()
    
    if not spy_data:
        logging.error("No SPY data found!")
        return 0, 0, []
    
    spy_dates = [row['date'] for row in reversed(spy_data)]
    spy_prices = pd.Series([float(row['close']) for row in reversed(spy_data)], index=spy_dates)
    
    # Process each symbol
    for idx, symbol in enumerate(symbols):
        try:
            if (idx + 1) % 500 == 0:
                logging.info(f"Processing {idx + 1}/{total}")
            
            # Get stock price data
            cur.execute("""
                SELECT date, close FROM price_daily 
                WHERE symbol = %s 
                ORDER BY date DESC 
                LIMIT 252
            """, (symbol,))
            stock_data = cur.fetchall()
            
            if not stock_data or len(stock_data) < 30:
                failed.append(symbol)
                continue
            
            stock_dates = [row['date'] for row in reversed(stock_data)]
            stock_prices = pd.Series([float(row['close']) for row in reversed(stock_data)], index=stock_dates)
            
            # Calculate metrics
            alpha, tracking_error, active_return, info_ratio, rel_volatility = \
                calculate_relative_metrics(stock_prices, spy_prices)
            
            if alpha is None:
                failed.append(symbol)
                continue
            
            # Update positioning_metrics or insert into new table
            cur.execute("""
                UPDATE positioning_metrics 
                SET 
                    alpha = %s,
                    tracking_error = %s,
                    active_return = %s,
                    information_ratio = %s,
                    rel_volatility = %s,
                    updated_at = NOW()
                WHERE symbol = %s
            """, (
                float(alpha) if alpha else None,
                float(tracking_error) if tracking_error else None,
                float(active_return) if active_return else None,
                float(info_ratio) if info_ratio else None,
                float(rel_volatility) if rel_volatility else None,
                symbol
            ))
            
            processed += 1
            
        except Exception as e:
            logging.warning(f"Error processing {symbol}: {e}")
            failed.append(symbol)
    
    conn.commit()
    return total, processed, failed

def create_columns(cur, conn):
    """Add relative performance columns to positioning_metrics if needed"""
    try:
        cur.execute("""
            ALTER TABLE positioning_metrics 
            ADD COLUMN IF NOT EXISTS alpha NUMERIC,
            ADD COLUMN IF NOT EXISTS tracking_error NUMERIC,
            ADD COLUMN IF NOT EXISTS active_return NUMERIC,
            ADD COLUMN IF NOT EXISTS information_ratio NUMERIC,
            ADD COLUMN IF NOT EXISTS rel_volatility NUMERIC;
        """)
        conn.commit()
        logging.info("✅ Relative performance columns created/verified")
    except Exception as e:
        logging.info(f"Columns may already exist: {e}")

if __name__ == "__main__":
    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create columns
    create_columns(cur, conn)
    
    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    
    if stock_syms:
        t_s, p_s, f_s = load_relative_performance(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")
    
    # Record last run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()
    
    cur.close()
    conn.close()
    logging.info("All done.")
