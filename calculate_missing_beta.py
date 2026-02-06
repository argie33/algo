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
import os
import json
import boto3
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration - works in AWS and locally."""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logger.info("Using AWS Secrets Manager for database config")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed: {str(e)[:100]}. Falling back to environment variables.")

    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "stocks")
    }

def get_connection():
    """Connect to database"""
    try:
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=30
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

def get_price_data(conn, symbol, days=504):
    """Get price data for last 504 trading days (2 years) to capture more stocks"""
    cur = conn.cursor()
    cur.execute("""
        SELECT date, close FROM price_daily
        WHERE symbol = %s
        ORDER BY date DESC LIMIT %s
    """, (symbol, days))
    data = cur.fetchall()
    cur.close()

    if len(data) < 10:  # Reduced minimum from 20 to 10 to capture more stocks
        return None
    
    df = pd.DataFrame(data, columns=['date', 'close'])
    df = df.sort_values('date')
    df['returns'] = df['close'].pct_change()
    return df[['date', 'returns']].dropna()

def get_market_returns(conn, days=504):
    """Get SPY (market proxy) returns for 504 trading days (2 years)"""
    cur = conn.cursor()
    cur.execute("""
        SELECT date, close FROM price_daily
        WHERE symbol = 'SPY'
        ORDER BY date DESC LIMIT %s
    """, (days,))
    data = cur.fetchall()
    cur.close()

    if len(data) < 10:  # Reduced minimum from 20 to 10
        return None
    
    df = pd.DataFrame(data, columns=['date', 'close'])
    df = df.sort_values('date')
    df['market_returns'] = df['close'].pct_change()
    return df[['date', 'market_returns']].dropna()

def calculate_beta(stock_returns, market_returns):
    """Calculate beta using regression with relaxed minimums"""
    if len(stock_returns) < 10 or len(market_returns) < 10:
        return None

    # Align dates
    merged = pd.merge(stock_returns, market_returns, on='date', how='inner')

    if len(merged) < 10:  # Reduced minimum matching dates from 20 to 10
        return None
    
    returns = merged['returns'].values
    market = merged['market_returns'].values
    
    # Calculate beta = covariance(stock, market) / variance(market)
    if np.var(market) == 0:
        return None
    
    beta = np.cov(returns, market)[0, 1] / np.var(market)
    
    # Validate beta
    if np.isnan(beta) or np.isinf(beta):
        return None
    
    return beta

def update_missing_betas(conn, symbols):
    """Calculate and save beta for missing stocks"""
    market_returns = get_market_returns(conn)
    
    if market_returns is None:
        logger.error("Cannot get market returns - SPY data missing")
        return
    
    calculated = 0
    failed = 0
    betas = {}  # Collect all calculated betas first
    
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
            
            # Validate reasonable range (relaxed to [-15, 15])
            if beta < -15 or beta > 15:
                logger.warning(f"{symbol}: Beta {beta:.3f} outside extreme range [-15, 15]")
                failed += 1
                continue
            
            betas[symbol] = beta
            calculated += 1
            
            if (i + 1) % 100 == 0:
                logger.info(f"Processed {i + 1}/{len(symbols)} symbols ({calculated} calculated, {failed} failed)")
            
        except Exception as e:
            logger.error(f"❌ {symbol}: {e}")
            failed += 1
    
    logger.info(f"Calculated betas for {calculated} symbols, {failed} failed")
    
    # Now batch insert/update all betas
    if betas:
        logger.info(f"Updating database with {len(betas)} beta values...")
        try:
            cur = conn.cursor()
            
            # Create temp table for batch update
            cur.execute("""
                CREATE TEMP TABLE beta_updates (
                    symbol VARCHAR(20),
                    beta DOUBLE PRECISION
                )
            """)
            
            # Insert calculated betas (convert to Python float to avoid numpy type issues)
            for symbol, beta in betas.items():
                cur.execute(
                    "INSERT INTO beta_updates (symbol, beta) VALUES (%s, %s)",
                    (symbol, float(beta))
                )
            
            # Batch update
            cur.execute("""
                UPDATE stability_metrics sm
                SET beta = bu.beta
                FROM beta_updates bu
                WHERE sm.symbol = bu.symbol AND sm.beta IS NULL
            """)
            
            rows_updated = cur.rowcount
            conn.commit()
            cur.close()
            
            logger.info(f"✅ Updated {rows_updated} rows in stability_metrics")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Batch update failed: {e}")
    
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
    logger.info("✅ Complete")

if __name__ == "__main__":
    main()
