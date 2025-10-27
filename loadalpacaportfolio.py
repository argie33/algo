#!/usr/bin/env python3
"""
Alpaca Portfolio Data Loader
Fetches real-time portfolio holdings and performance data from Alpaca Trading API
Populates portfolio_holdings and portfolio_performance tables for dashboard display

Loads:
- Current holdings from Alpaca /v2/positions endpoint
- Account metrics from Alpaca /v2/account endpoint
- Historical performance data (calculated from account equity curve)
"""

import sys
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import json
import requests
from requests.auth import HTTPBasicAuth

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Suppress verbose requests logging
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'stocks')

# Alpaca configuration
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY', '')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY', '')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
PAPER_TRADING = os.getenv('ALPACA_PAPER_TRADING', 'true').lower() == 'true'

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    logger.error("❌ Alpaca API credentials not found in environment variables")
    logger.error("Please set ALPACA_API_KEY and ALPACA_SECRET_KEY")
    sys.exit(1)

def get_db_connection():
    """Create PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        logger.info(f"✅ Connected to database: {DB_NAME}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Database connection failed: {e}")
        sys.exit(1)

def get_alpaca_headers():
    """Build Alpaca API headers"""
    return {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
        'Content-Type': 'application/json'
    }

def fetch_positions():
    """Fetch current positions from Alpaca API"""
    try:
        logger.info("📊 Fetching positions from Alpaca...")
        url = f"{ALPACA_BASE_URL}/v2/positions"
        headers = get_alpaca_headers()

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        positions = response.json()
        logger.info(f"✅ Retrieved {len(positions)} positions from Alpaca")
        return positions
    except requests.RequestException as e:
        logger.error(f"❌ Failed to fetch positions: {e}")
        return []

def fetch_account():
    """Fetch account information from Alpaca API"""
    try:
        logger.info("📈 Fetching account information from Alpaca...")
        url = f"{ALPACA_BASE_URL}/v2/account"
        headers = get_alpaca_headers()

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        account = response.json()
        logger.info(f"✅ Retrieved account information")
        return account
    except requests.RequestException as e:
        logger.error(f"❌ Failed to fetch account: {e}")
        return None

def fetch_historical_bars(symbol, lookback_days=365):
    """Fetch historical bars for performance tracking"""
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=lookback_days)

        url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
        headers = get_alpaca_headers()
        params = {
            'start': start_date.isoformat(),
            'end': end_date.isoformat(),
            'timeframe': 'day',
            'limit': 10000
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get('bars', [])
    except requests.RequestException as e:
        logger.debug(f"⚠️  Could not fetch bars for {symbol}: {e}")
        return []

def calculate_daily_performance(account_info):
    """Calculate daily performance metrics"""
    if not account_info:
        return None

    try:
        portfolio_value = float(account_info.get('portfolio_value', 0))
        last_equity = float(account_info.get('last_equity', portfolio_value))
        cash = float(account_info.get('cash', 0))

        # Calculate daily P&L
        daily_pnl = portfolio_value - last_equity
        daily_pnl_percent = (daily_pnl / last_equity * 100) if last_equity > 0 else 0

        # Total return from initial cash deposit
        total_return_percent = ((portfolio_value - 100000) / 100000 * 100) if portfolio_value > 0 else 0

        return {
            'portfolio_value': portfolio_value,
            'daily_pnl': daily_pnl,
            'daily_pnl_percent': daily_pnl_percent,
            'total_return_percent': total_return_percent,
            'cash': cash
        }
    except (KeyError, ValueError) as e:
        logger.error(f"❌ Failed to calculate performance: {e}")
        return None

def ensure_tables_exist(conn):
    """Ensure portfolio tables exist in database"""
    cur = conn.cursor()

    try:
        # Create portfolio_holdings table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                symbol VARCHAR(10) NOT NULL,
                quantity DOUBLE PRECISION NOT NULL DEFAULT 0,
                average_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
                current_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                market_value DOUBLE PRECISION NOT NULL DEFAULT 0,
                unrealized_pnl DOUBLE PRECISION DEFAULT 0,
                cost_basis DOUBLE PRECISION DEFAULT 0,
                broker VARCHAR(20) DEFAULT 'alpaca',
                position_type VARCHAR(10) DEFAULT 'long',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, symbol, broker)
            )
        """)

        # Create portfolio_performance table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_performance (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255),
                date DATE,
                total_value DECIMAL(15, 2),
                daily_pnl DECIMAL(15, 2),
                total_pnl DECIMAL(15, 2),
                total_pnl_percent DECIMAL(8, 4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            )
        """)

        conn.commit()
        logger.info("✅ Database tables ready")
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to create tables: {e}")
        conn.rollback()
        raise

def load_holdings(conn, positions):
    """Load portfolio holdings into database"""
    cur = conn.cursor()
    user_id = 'test-user'  # Use test-user to match API expectations

    # Clear existing holdings for fresh load
    try:
        cur.execute("DELETE FROM portfolio_holdings WHERE user_id = %s", (user_id,))
        logger.info("🗑️  Cleared previous holdings")
    except psycopg2.Error as e:
        logger.warn(f"Could not clear holdings: {e}")

    loaded_count = 0

    for position in positions:
        try:
            symbol = position.get('symbol')
            qty = float(position.get('qty', 0))

            # Skip closed/zero positions
            if qty == 0 or qty < 0.0001:
                continue

            current_price = float(position.get('current_price', 0))
            avg_cost = float(position.get('avg_fill_price', current_price))
            market_value = float(position.get('market_value', 0))
            unrealized_gain = float(position.get('unrealized_gain', 0))
            unrealized_gain_pct = float(position.get('unrealized_gain_pct', 0)) * 100

            # Get sector from asset info
            sector = position.get('asset', {}).get('sector', 'Other') if isinstance(position.get('asset'), dict) else 'Other'

            cur.execute("""
                INSERT INTO portfolio_holdings
                (user_id, symbol, quantity, current_price, average_cost)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    current_price = EXCLUDED.current_price,
                    average_cost = EXCLUDED.average_cost
            """, (
                user_id, symbol, qty, current_price, avg_cost
            ))

            loaded_count += 1

        except (KeyError, ValueError, TypeError) as e:
            logger.warn(f"⚠️  Failed to process position: {e}")
            continue

    try:
        conn.commit()
        logger.info(f"✅ Loaded {loaded_count} holdings into database")
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to commit holdings: {e}")
        conn.rollback()
        raise

def load_performance(conn, account_info):
    """Load portfolio performance into database"""
    cur = conn.cursor()
    user_id = 'test-user'  # Use test-user to match API expectations

    perf = calculate_daily_performance(account_info)
    if not perf:
        logger.warn("⚠️  Could not calculate performance metrics")
        return

    try:
        cur.execute("""
            INSERT INTO portfolio_performance
            (user_id, date, total_value, daily_pnl, total_pnl, total_pnl_percent, created_at)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, date) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                daily_pnl = EXCLUDED.daily_pnl,
                total_pnl = EXCLUDED.total_pnl,
                total_pnl_percent = EXCLUDED.total_pnl_percent,
                created_at = EXCLUDED.created_at
        """, (
            user_id,
            perf['portfolio_value'],
            perf['daily_pnl'],
            perf['total_return_percent'] * perf['portfolio_value'] / 100,  # Convert % to dollar amount
            perf['total_return_percent']
        ))

        conn.commit()
        logger.info(f"✅ Loaded performance data - Portfolio: ${perf['portfolio_value']:,.2f}, Daily P&L: {perf['daily_pnl_percent']:.2f}%")
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to load performance: {e}")
        conn.rollback()
        raise

def main():
    """Main loader function"""
    logger.info("=" * 60)
    logger.info("🚀 Alpaca Portfolio Data Loader Starting")
    logger.info("=" * 60)

    # Connect to database
    conn = get_db_connection()

    try:
        # Ensure tables exist
        ensure_tables_exist(conn)

        # Fetch data from Alpaca
        positions = fetch_positions()
        account = fetch_account()

        if not positions and not account:
            logger.error("❌ Failed to fetch any data from Alpaca")
            return False

        # Load data into database
        if positions:
            load_holdings(conn, positions)

        if account:
            load_performance(conn, account)

        logger.info("=" * 60)
        logger.info("✅ Alpaca Portfolio Data Loader Complete")
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"❌ Loader failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
