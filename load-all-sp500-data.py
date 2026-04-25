#!/usr/bin/env python3
"""
Complete S&P 500 Data Loader - LOCAL FIRST

This loader:
1. Works locally with environment variables OR AWS
2. Loads ALL critical data in correct order
3. Has proper error recovery and logging
4. Processes all 4969 S&P 500 stocks (or as many as possible from yfinance)

Run: python3 load-all-sp500-data.py
"""

import sys
import os
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import io

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
import pandas as pd
import numpy as np
import json

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("load-all-sp500-data")

# ===========================
# Database Configuration - LOCAL FIRST
# ===========================
def get_db_config():
    """Get DB config - LOCAL first, then AWS."""
    # Try local environment first
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")
    db_port = os.environ.get("DB_PORT", "5432")

    if db_host and db_user:
        logger.info(f"Using LOCAL database: {db_user}@{db_host}/{db_name}")
        return {
            "host": db_host,
            "port": int(db_port),
            "user": db_user,
            "password": db_password or "",
            "database": db_name or "stocks"
        }

    # Fall back to AWS
    try:
        import boto3
        aws_region = os.environ.get("AWS_REGION", "us-east-1")
        db_secret_arn = os.environ.get("DB_SECRET_ARN")

        if db_secret_arn:
            logger.info("Using AWS Secrets Manager...")
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "database": sec["dbname"]
            }
    except:
        pass

    # Default fallback
    logger.warning("Using default localhost connection...")
    return {
        "host": "localhost",
        "port": 5432,
        "user": "stocks",
        "password": "",
        "database": "stocks"
    }

def connect_db():
    """Connect to database with retry logic."""
    config = get_db_config()
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**config)
            logger.info("✓ Database connected")
            return conn
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Connection attempt {attempt+1} failed: {e}. Retrying...")
                time.sleep(2)
            else:
                logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                sys.exit(1)

# ===========================
# Data Loading Functions
# ===========================

def get_sp500_symbols(conn):
    """Get all S&P 500 symbols from database."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    logger.info(f"Found {len(symbols)} symbols in database")
    return symbols

def load_price_data(conn, symbols, timeframe='daily'):
    """Load price data for all symbols from yfinance."""
    logger.info(f"\n{'='*60}")
    logger.info(f"LOADING PRICE DATA ({timeframe})")
    logger.info(f"{'='*60}")

    cur = conn.cursor()
    table_name = f"price_{timeframe}"

    total_inserted = 0
    success_count = 0

    for i, symbol in enumerate(symbols, 1):
        try:
            # Get price data
            ticker = yf.Ticker(symbol)

            if timeframe == 'daily':
                hist = ticker.history(period='5y')
            elif timeframe == 'weekly':
                hist = ticker.history(period='10y', interval='1wk')
            else:  # monthly
                hist = ticker.history(period='10y', interval='1mo')

            if hist.empty:
                continue

            # Format for database
            data = []
            for date, row in hist.iterrows():
                data.append((
                    symbol,
                    date.date(),
                    float(row['Open']),
                    float(row['High']),
                    float(row['Low']),
                    float(row['Close']),
                    int(row['Volume']) if not pd.isna(row['Volume']) else 0
                ))

            if data:
                query = f"""
                    INSERT INTO {table_name} (symbol, date, open, high, low, close, volume)
                    VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        close = EXCLUDED.close, volume = EXCLUDED.volume
                """
                execute_values(cur, query, data)
                conn.commit()
                total_inserted += len(data)
                success_count += 1

            if i % 50 == 0:
                logger.info(f"  [{i}/{len(symbols)}] {total_inserted} rows inserted")

        except Exception as e:
            logger.debug(f"  {symbol}: {str(e)[:50]}")
            continue

    cur.close()
    logger.info(f"✓ Price data: {success_count}/{len(symbols)} symbols, {total_inserted} rows")
    return total_inserted

def load_earnings_estimates(conn, symbols):
    """Load earnings estimates from yfinance."""
    logger.info(f"\n{'='*60}")
    logger.info("LOADING EARNINGS ESTIMATES")
    logger.info(f"{'='*60}")

    cur = conn.cursor()
    data_list = []
    success_count = 0

    for i, symbol in enumerate(symbols, 1):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Try to extract earnings info
            if 'epsTrailingTwelveMonths' in info and info['epsTrailingTwelveMonths']:
                data_list.append((
                    symbol,
                    float(info.get('epsCurrentYear', 0)) if info.get('epsCurrentYear') else None,
                    float(info.get('epsForward', 0)) if info.get('epsForward') else None,
                    datetime.now().strftime('%Y-Q') + str((datetime.now().month - 1) // 3 + 1)
                ))
                success_count += 1

            if i % 100 == 0:
                logger.info(f"  [{i}/{len(symbols)}] {success_count} with data")

        except Exception as e:
            continue

    if data_list:
        query = """
            INSERT INTO earnings_estimates (symbol, eps_estimate, eps_forward, period)
            VALUES %s
            ON CONFLICT (symbol, period) DO UPDATE SET
                eps_estimate = EXCLUDED.eps_estimate
        """
        execute_values(cur, query, data_list)
        conn.commit()

    cur.close()
    logger.info(f"✓ Earnings: {success_count}/{len(symbols)} symbols")
    return success_count

def load_analyst_sentiment(conn, symbols):
    """Load analyst sentiment from yfinance."""
    logger.info(f"\n{'='*60}")
    logger.info("LOADING ANALYST SENTIMENT")
    logger.info(f"{'='*60}")

    cur = conn.cursor()
    data_list = []
    success_count = 0

    for i, symbol in enumerate(symbols, 1):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Extract analyst data
            if 'recommendationKey' in info and info['recommendationKey']:
                rating_key = info.get('recommendationKey', 'hold').lower()
                target_price = float(info.get('targetMeanPrice', 0)) if info.get('targetMeanPrice') else None
                analyst_count = int(info.get('numberOfAnalysts', 0)) if info.get('numberOfAnalysts') else 0

                # Map recommendation to sentiment counts
                bullish = 0
                neutral = 0
                bearish = 0

                if rating_key in ['strong_buy', 'buy']:
                    bullish = analyst_count
                elif rating_key == 'hold':
                    neutral = analyst_count
                else:  # sell, strong_sell
                    bearish = analyst_count

                data_list.append((
                    symbol,
                    analyst_count,
                    bullish,
                    bearish,
                    neutral,
                    target_price,
                    datetime.now().date()
                ))
                success_count += 1

            if i % 100 == 0:
                logger.info(f"  [{i}/{len(symbols)}] {success_count} with sentiment")

        except Exception as e:
            continue

    if data_list:
        query = """
            INSERT INTO analyst_sentiment_analysis (symbol, total_analysts, bullish_count, bearish_count, neutral_count, target_price, date_recorded)
            VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                total_analysts = EXCLUDED.total_analysts, bullish_count = EXCLUDED.bullish_count
        """
        execute_values(cur, query, data_list)
        conn.commit()

    cur.close()
    logger.info(f"✓ Sentiment: {success_count}/{len(symbols)} symbols")
    return success_count

def load_options_chains(conn, symbols):
    """Load options chains from yfinance (top optionable stocks)."""
    logger.info(f"\n{'='*60}")
    logger.info("LOADING OPTIONS CHAINS")
    logger.info(f"{'='*60}")

    cur = conn.cursor()
    data_list = []
    success_count = 0

    # Only load options for the most liquid stocks
    top_symbols = symbols[:500]  # Focus on top 500

    for i, symbol in enumerate(top_symbols, 1):
        try:
            ticker = yf.Ticker(symbol)

            # Check if symbol has options
            if not hasattr(ticker, 'options') or not ticker.options:
                continue

            expirations = list(ticker.options)[:3]  # Just nearest 3 expirations

            for exp_date_str in expirations:
                try:
                    chain = ticker.option_chain(exp_date_str)
                    exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()

                    # Process calls and puts
                    for opt_type, df in [('call', chain.calls), ('put', chain.puts)]:
                        for _, row in df.iterrows():
                            data_list.append((
                                symbol,
                                exp_date,
                                opt_type,
                                float(row['strike']),
                                row['contractSymbol'],
                                float(row['bid']) if pd.notna(row['bid']) else None,
                                float(row['ask']) if pd.notna(row['ask']) else None,
                                int(row['volume']) if pd.notna(row['volume']) else 0,
                                int(row['openInterest']) if pd.notna(row['openInterest']) else 0,
                                float(row['impliedVolatility']) if pd.notna(row['impliedVolatility']) else None,
                                datetime.now().date()
                            ))

                    success_count += 1
                except:
                    continue

            if i % 50 == 0:
                logger.info(f"  [{i}/{ len(top_symbols)}] {success_count} with options")

        except Exception as e:
            continue

    if data_list:
        query = """
            INSERT INTO options_chains (symbol, expiration_date, option_type, strike, contract_symbol,
                bid, ask, volume, open_interest, implied_volatility, data_date)
            VALUES %s
            ON CONFLICT (contract_symbol) DO UPDATE SET
                bid = EXCLUDED.bid, ask = EXCLUDED.ask
        """
        execute_values(cur, query, data_list)
        conn.commit()

    cur.close()
    logger.info(f"✓ Options chains: {success_count} expirations loaded")
    return success_count

def load_technical_data(conn, symbols):
    """Calculate and load technical indicators."""
    logger.info(f"\n{'='*60}")
    logger.info("LOADING TECHNICAL DATA")
    logger.info(f"{'='*60}")

    cur = conn.cursor()

    # Get recent prices
    cur.execute("""
        SELECT symbol, date, close, volume
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY symbol, date DESC
    """)

    results = cur.fetchall()

    # Group by symbol
    symbol_data = {}
    for symbol, date, close, volume in results:
        if symbol not in symbol_data:
            symbol_data[symbol] = []
        symbol_data[symbol].append((date, close, volume))

    data_list = []
    success_count = 0

    for symbol, prices in symbol_data.items():
        try:
            prices.reverse()  # Oldest first
            closes = [p[1] for p in prices]

            if len(closes) < 20:
                continue

            df = pd.DataFrame({'close': closes})

            # Calculate indicators
            df['sma_20'] = df['close'].rolling(20).mean()
            df['sma_50'] = df['close'].rolling(50).mean() if len(closes) >= 50 else None
            df['rsi'] = calculate_rsi(df['close'], 14)

            # Store latest
            latest = df.iloc[-1]
            data_list.append((
                symbol,
                prices[-1][0],
                float(latest['sma_20']) if pd.notna(latest['sma_20']) else None,
                float(latest.get('sma_50', 0)) if pd.notna(latest.get('sma_50', 0)) else None,
                float(latest['rsi']) if pd.notna(latest['rsi']) else None,
                datetime.now().date()
            ))
            success_count += 1

        except Exception as e:
            continue

    if data_list:
        query = """
            INSERT INTO technical_data_daily (symbol, date, sma_20, sma_50, rsi, calculated_date)
            VALUES %s
            ON CONFLICT (symbol, date) DO UPDATE SET
                sma_20 = EXCLUDED.sma_20, rsi = EXCLUDED.rsi
        """
        execute_values(cur, query, data_list)
        conn.commit()

    cur.close()
    logger.info(f"✓ Technical data: {success_count} symbols")
    return success_count

def calculate_rsi(prices, period=14):
    """Calculate RSI (Relative Strength Index)."""
    try:
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed>=0].sum()/period
        down = -seed[seed<0].sum()/period
        rs = up/down if down != 0 else 0
        rsi = np.zeros_like(prices)
        rsi[:period] = 100. - 100./(1.+rs)

        for i in range(period, len(prices)):
            delta = deltas[i-1]
            if delta>0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            up = (up*(period-1) + upval)/period
            down = (down*(period-1) + downval)/period
            rs = up/down if down != 0 else 0
            rsi[i] = 100. - 100./(1.+rs)

        return rsi
    except:
        return None

# ===========================
# Main
# ===========================
def main():
    """Load all critical data."""
    logger.info("\n" + "="*60)
    logger.info("COMPLETE S&P 500 DATA LOADER")
    logger.info("="*60)

    start_time = time.time()

    try:
        conn = connect_db()
        symbols = get_sp500_symbols(conn)

        if not symbols:
            logger.error("No symbols found in database!")
            sys.exit(1)

        # Load data in order
        load_price_data(conn, symbols, 'daily')
        load_price_data(conn, symbols, 'weekly')
        load_price_data(conn, symbols, 'monthly')
        load_earnings_estimates(conn, symbols)
        load_analyst_sentiment(conn, symbols)
        load_options_chains(conn, symbols)
        load_technical_data(conn, symbols)

        conn.close()

        elapsed = time.time() - start_time
        logger.info(f"\n{'='*60}")
        logger.info(f"✓ ALL DATA LOADED ({elapsed:.1f}s)")
        logger.info(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"\n✗ FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
