#!/usr/bin/env python3
"""
Load options chains from yfinance and calculate Greeks.

Updates:
- options_chains table: Raw options data from Yahoo Finance
- options_greeks table: Calculated Black-Scholes Greeks
- iv_history table: IV tracking for percentile calculations

This loader:
1. Creates all necessary tables (if they don't exist)
2. Fetches options chains from yfinance
3. Calculates Greeks using Black-Scholes
4. Stores data for covered call opportunities calculation
"""
import os
import sys
import json
import logging
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values
import boto3
import requests

# Import Greeks calculator
sys.path.insert(0, '/home/stocks/algo/utils')
try:
    from greeks_calculator import GreeksCalculator
except ImportError as e:
    print(f"Error importing greeks_calculator: {e}")
    sys.exit(1)

# ===========================
# Logging Setup
# ===========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("loadoptionschains")

# ===========================
# Database Configuration
# ===========================
def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables.

    Priority:
    1. AWS Secrets Manager (if DB_SECRET_ARN is set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    if db_secret_arn:
        try:
            client = boto3.client("secretsmanager")
            secret_str = client.get_secret_value(SecretId=db_secret_arn)["SecretString"]
            secret = json.loads(secret_str)
            logger.info("Using AWS Secrets Manager for database config")
            return {
                "host": secret["host"],
                "port": int(secret.get("port", 5432)),
                "user": secret["username"],
                "password": secret["password"],
                "dbname": secret["dbname"]
            }
        except Exception as e:
            logger.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    logger.info("Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

# ===========================
# Table Creation
# ===========================
def ensure_tables(cur, conn):
    """Create options tables if they don't exist."""

    logger.info("Creating options tables if they don't exist...")

    # 1. Options chains table - raw data from yfinance
    cur.execute("""
        CREATE TABLE IF NOT EXISTS options_chains (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            expiration_date DATE NOT NULL,
            option_type VARCHAR(4) NOT NULL CHECK (option_type IN ('call', 'put')),
            strike REAL NOT NULL,
            contract_symbol VARCHAR(50) NOT NULL UNIQUE,
            last_price REAL,
            bid REAL,
            ask REAL,
            change REAL,
            percent_change REAL,
            volume BIGINT,
            open_interest BIGINT,
            implied_volatility REAL,
            in_the_money BOOLEAN,
            contract_size VARCHAR(20),
            currency VARCHAR(10) DEFAULT 'USD',
            last_trade_date TIMESTAMP,
            fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_date DATE NOT NULL
        );
    """)

    # Create indexes for options_chains
    cur.execute("CREATE INDEX IF NOT EXISTS idx_options_chains_symbol_exp ON options_chains(symbol, expiration_date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_options_chains_symbol_type ON options_chains(symbol, option_type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_options_chains_data_date ON options_chains(data_date DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_options_chains_contract ON options_chains(contract_symbol);")

    # 2. Options Greeks table - calculated values
    cur.execute("""
        CREATE TABLE IF NOT EXISTS options_greeks (
            id SERIAL PRIMARY KEY,
            contract_symbol VARCHAR(50) NOT NULL,
            symbol VARCHAR(20) NOT NULL,
            expiration_date DATE NOT NULL,
            strike REAL NOT NULL,
            option_type VARCHAR(4) NOT NULL,
            delta REAL,
            gamma REAL,
            theta REAL,
            vega REAL,
            rho REAL,
            stock_price REAL NOT NULL,
            risk_free_rate REAL NOT NULL,
            implied_volatility REAL NOT NULL,
            days_to_expiration INTEGER NOT NULL,
            theoretical_value REAL,
            intrinsic_value REAL,
            extrinsic_value REAL,
            calculated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            data_date DATE NOT NULL,
            UNIQUE(contract_symbol, data_date)
        );
    """)

    # Create indexes for options_greeks
    cur.execute("CREATE INDEX IF NOT EXISTS idx_greeks_symbol_exp ON options_greeks(symbol, expiration_date);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_greeks_data_date ON options_greeks(data_date DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_greeks_contract ON options_greeks(contract_symbol);")

    # 3. IV history table - for IV percentile calculations
    cur.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            iv_30day REAL,
            iv_60day REAL,
            iv_percentile_30 REAL,
            iv_percentile_60 REAL,
            UNIQUE(symbol, date)
        );
    """)

    # Create indexes for iv_history
    cur.execute("CREATE INDEX IF NOT EXISTS idx_iv_history_symbol_date ON iv_history(symbol, date DESC);")

    conn.commit()
    logger.info("✅ All options tables ensured")

# ===========================
# Data Fetching Functions
# ===========================
def get_risk_free_rate():
    """Fetch risk-free rate from FRED API (13-week Treasury Bill)."""
    fred_api_key = os.environ.get('FRED_API_KEY', '')

    if not fred_api_key:
        logger.warning("FRED_API_KEY not set, using default 4.5%")
        return 0.045

    try:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': 'DTB3',  # 3-Month Treasury Bill
            'api_key': fred_api_key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 1
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if 'observations' in data and len(data['observations']) > 0:
            rate = float(data['observations'][0]['value']) / 100
            logger.info(f"✅ Risk-free rate: {rate:.4f} ({rate*100:.2f}%)")
            return rate
        else:
            logger.warning("No FRED data, using default 4.5%")
            return 0.045

    except Exception as e:
        logger.error(f"Error fetching risk-free rate: {e}")
        return 0.045

def get_active_symbols(conn):
    """Get symbols that have recent price data."""
    query = """
        SELECT DISTINCT symbol
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        ORDER BY symbol
    """
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            symbols = [row[0] for row in cur.fetchall()]
        logger.info(f"✅ Found {len(symbols)} symbols with recent price data")
        return symbols
    except Exception as e:
        logger.error(f"Error getting active symbols: {e}")
        return []

# ===========================
# Options Loading
# ===========================
def load_options_for_symbol(symbol, risk_free_rate, data_date, conn):
    """Load options chain for a single symbol."""
    try:
        ticker = yf.Ticker(symbol)

        # Get current stock price
        hist = ticker.history(period='1d')
        if hist.empty:
            logger.warning(f"{symbol}: No price data available")
            return 0

        stock_price = float(hist['Close'].iloc[-1])

        # Get options expirations
        if not hasattr(ticker, 'options') or not ticker.options:
            logger.debug(f"{symbol}: No options available")
            return 0

        expirations = list(ticker.options)

        # Limit to next 6 months
        cutoff_date = datetime.now() + timedelta(days=180)
        expirations = [
            exp for exp in expirations
            if datetime.strptime(exp, '%Y-%m-%d') <= cutoff_date
        ]

        if not expirations:
            logger.debug(f"{symbol}: No expirations in next 6 months")
            return 0

        logger.info(f"Loading {symbol}: {len(expirations)} expirations, price ${stock_price:.2f}")

        chains_data = []
        greeks_data = []

        # Process each expiration
        for exp_date_str in expirations:
            try:
                chain = ticker.option_chain(exp_date_str)
                exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
                days_to_exp = (exp_date - data_date).days
                years_to_exp = days_to_exp / 365.0

                # Process calls
                for _, row in chain.calls.iterrows():
                    chains_data.append(extract_option_row(
                        row, symbol, exp_date, 'call', data_date
                    ))

                    # Calculate Greeks
                    if pd.notna(row['impliedVolatility']) and row['impliedVolatility'] > 0:
                        greeks = GreeksCalculator.calculate_greeks(
                            S=stock_price,
                            K=float(row['strike']),
                            T=years_to_exp,
                            r=risk_free_rate,
                            sigma=float(row['impliedVolatility']),
                            option_type='call'
                        )

                        if greeks:
                            greeks_data.append({
                                'contract_symbol': row['contractSymbol'],
                                'symbol': symbol,
                                'expiration_date': exp_date,
                                'strike': float(row['strike']),
                                'option_type': 'call',
                                'delta': greeks['delta'],
                                'gamma': greeks['gamma'],
                                'theta': greeks['theta'],
                                'vega': greeks['vega'],
                                'rho': greeks['rho'],
                                'stock_price': stock_price,
                                'risk_free_rate': risk_free_rate,
                                'implied_volatility': float(row['impliedVolatility']),
                                'days_to_expiration': days_to_exp,
                                'theoretical_value': greeks['theoretical_value'],
                                'intrinsic_value': greeks['intrinsic_value'],
                                'extrinsic_value': greeks['extrinsic_value'],
                                'data_date': data_date
                            })

                # Process puts
                for _, row in chain.puts.iterrows():
                    chains_data.append(extract_option_row(
                        row, symbol, exp_date, 'put', data_date
                    ))

                    if pd.notna(row['impliedVolatility']) and row['impliedVolatility'] > 0:
                        greeks = GreeksCalculator.calculate_greeks(
                            S=stock_price,
                            K=float(row['strike']),
                            T=years_to_exp,
                            r=risk_free_rate,
                            sigma=float(row['impliedVolatility']),
                            option_type='put'
                        )

                        if greeks:
                            greeks_data.append({
                                'contract_symbol': row['contractSymbol'],
                                'symbol': symbol,
                                'expiration_date': exp_date,
                                'strike': float(row['strike']),
                                'option_type': 'put',
                                'delta': greeks['delta'],
                                'gamma': greeks['gamma'],
                                'theta': greeks['theta'],
                                'vega': greeks['vega'],
                                'rho': greeks['rho'],
                                'stock_price': stock_price,
                                'risk_free_rate': risk_free_rate,
                                'implied_volatility': float(row['impliedVolatility']),
                                'days_to_expiration': days_to_exp,
                                'theoretical_value': greeks['theoretical_value'],
                                'intrinsic_value': greeks['intrinsic_value'],
                                'extrinsic_value': greeks['extrinsic_value'],
                                'data_date': data_date
                            })

            except Exception as e:
                logger.error(f"{symbol} exp {exp_date_str}: {e}")
                continue

        # Bulk insert
        if chains_data:
            insert_options_chains(conn, chains_data)

        if greeks_data:
            insert_options_greeks(conn, greeks_data)

        return len(chains_data)

    except Exception as e:
        logger.error(f"Error loading {symbol}: {e}")
        return 0

def extract_option_row(row, symbol, exp_date, opt_type, data_date):
    """Extract option data from yfinance DataFrame row."""
    return {
        'symbol': symbol,
        'expiration_date': exp_date,
        'option_type': opt_type,
        'strike': float(row['strike']),
        'contract_symbol': row['contractSymbol'],
        'last_price': float(row['lastPrice']) if pd.notna(row['lastPrice']) else None,
        'bid': float(row['bid']) if pd.notna(row['bid']) else None,
        'ask': float(row['ask']) if pd.notna(row['ask']) else None,
        'change': float(row['change']) if pd.notna(row['change']) else None,
        'percent_change': float(row['percentChange']) if pd.notna(row['percentChange']) else None,
        'volume': int(row['volume']) if pd.notna(row['volume']) else None,
        'open_interest': int(row['openInterest']) if pd.notna(row['openInterest']) else None,
        'implied_volatility': float(row['impliedVolatility']) if pd.notna(row['impliedVolatility']) else None,
        'in_the_money': bool(row['inTheMoney']) if pd.notna(row['inTheMoney']) else False,
        'contract_size': row.get('contractSize', 'REGULAR'),
        'currency': row.get('currency', 'USD'),
        'last_trade_date': pd.to_datetime(row['lastTradeDate']) if pd.notna(row.get('lastTradeDate')) else None,
        'data_date': data_date
    }

# ===========================
# Database Insert Functions
# ===========================
def insert_options_chains(conn, data):
    """Bulk insert options chains with conflict handling."""
    query = """
        INSERT INTO options_chains (
            symbol, expiration_date, option_type, strike, contract_symbol,
            last_price, bid, ask, change, percent_change,
            volume, open_interest, implied_volatility,
            in_the_money, contract_size, currency,
            last_trade_date, data_date
        ) VALUES %s
        ON CONFLICT (contract_symbol)
        DO UPDATE SET
            last_price = EXCLUDED.last_price,
            bid = EXCLUDED.bid,
            ask = EXCLUDED.ask,
            change = EXCLUDED.change,
            percent_change = EXCLUDED.percent_change,
            volume = EXCLUDED.volume,
            open_interest = EXCLUDED.open_interest,
            implied_volatility = EXCLUDED.implied_volatility,
            in_the_money = EXCLUDED.in_the_money,
            last_trade_date = EXCLUDED.last_trade_date,
            fetched_at = CURRENT_TIMESTAMP
    """

    values = [(
        d['symbol'], d['expiration_date'], d['option_type'], d['strike'], d['contract_symbol'],
        d['last_price'], d['bid'], d['ask'], d['change'], d['percent_change'],
        d['volume'], d['open_interest'], d['implied_volatility'],
        d['in_the_money'], d['contract_size'], d['currency'],
        d['last_trade_date'], d['data_date']
    ) for d in data]

    with conn.cursor() as cur:
        execute_values(cur, query, values)
        conn.commit()

    logger.info(f"✅ Inserted {len(data)} option chains")

def insert_options_greeks(conn, data):
    """Bulk insert Greeks with conflict handling."""
    query = """
        INSERT INTO options_greeks (
            contract_symbol, symbol, expiration_date, strike, option_type,
            delta, gamma, theta, vega, rho,
            stock_price, risk_free_rate, implied_volatility, days_to_expiration,
            theoretical_value, intrinsic_value, extrinsic_value, data_date
        ) VALUES %s
        ON CONFLICT (contract_symbol, data_date)
        DO UPDATE SET
            delta = EXCLUDED.delta,
            gamma = EXCLUDED.gamma,
            theta = EXCLUDED.theta,
            vega = EXCLUDED.vega,
            rho = EXCLUDED.rho,
            stock_price = EXCLUDED.stock_price,
            theoretical_value = EXCLUDED.theoretical_value,
            intrinsic_value = EXCLUDED.intrinsic_value,
            extrinsic_value = EXCLUDED.extrinsic_value,
            calculated_at = CURRENT_TIMESTAMP
    """

    values = [(
        d['contract_symbol'], d['symbol'], d['expiration_date'], d['strike'], d['option_type'],
        d['delta'], d['gamma'], d['theta'], d['vega'], d['rho'],
        d['stock_price'], d['risk_free_rate'], d['implied_volatility'], d['days_to_expiration'],
        d['theoretical_value'], d['intrinsic_value'], d['extrinsic_value'], d['data_date']
    ) for d in data]

    with conn.cursor() as cur:
        execute_values(cur, query, values)
        conn.commit()

    logger.info(f"✅ Inserted {len(data)} Greeks")

# ===========================
# Main Entry Point
# ===========================
def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("🚀 STARTING OPTIONS CHAIN LOADER")
    logger.info("=" * 60)

    try:
        # Get database connection
        db_config = get_db_config()
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Ensure tables exist
        ensure_tables(cur, conn)

        # Get risk-free rate
        risk_free_rate = get_risk_free_rate()
        data_date = date.today()

        # Get symbols to process
        symbols = get_active_symbols(conn)
        if not symbols:
            logger.warning("No symbols found to process")
            return

        logger.info(f"Processing {len(symbols)} symbols...")

        total_options = 0
        success_count = 0
        failed_symbols = []

        # Process each symbol
        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info(f"[{i}/{len(symbols)}] {symbol}")
                count = load_options_for_symbol(symbol, risk_free_rate, data_date, conn)
                if count > 0:
                    total_options += count
                    success_count += 1
                else:
                    logger.debug(f"  → No options loaded")
            except Exception as e:
                logger.error(f"  ✗ Failed: {e}")
                failed_symbols.append(symbol)

        # Update metadata
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run, records_loaded)
                VALUES (%s, CURRENT_TIMESTAMP, %s)
                ON CONFLICT (script_name)
                DO UPDATE SET last_run = CURRENT_TIMESTAMP, records_loaded = EXCLUDED.records_loaded
            """, ('loadoptionschains', total_options))
            conn.commit()

        conn.close()

        logger.info("=" * 60)
        logger.info(f"✅ COMPLETE: {success_count}/{len(symbols)} symbols processed")
        logger.info(f"📊 Total options loaded: {total_options}")
        if failed_symbols:
            logger.warning(f"⚠️  Failed symbols ({len(failed_symbols)}): {', '.join(failed_symbols[:5])}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
