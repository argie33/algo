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

# Portfolio owner user ID - MUST be set to real user, never use test user
PORTFOLIO_USER_ID = os.getenv('PORTFOLIO_USER_ID', '')

if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
    logger.error("❌ Alpaca API credentials not found in environment variables")
    logger.error("Please set ALPACA_API_KEY and ALPACA_SECRET_KEY")
    sys.exit(1)

if not PORTFOLIO_USER_ID:
    logger.error("❌ Portfolio user ID not found in environment variables")
    logger.error("Please set PORTFOLIO_USER_ID to the real user account ID")
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

def fetch_account_equity_history():
    """Fetch account equity history from Alpaca for portfolio performance tracking"""
    try:
        logger.info("📈 Fetching account portfolio history from Alpaca...")
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history"
        headers = get_alpaca_headers()

        # Get last 365 days of history with daily timeframe
        params = {
            'period': '1y',  # Last year of data
            'timeframe': 'day',
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        logger.info(f"✅ Retrieved account portfolio history")
        return data
    except requests.RequestException as e:
        logger.warn(f"⚠️  Could not fetch portfolio history: {e}")
        return None

def fetch_orders():
    """Fetch completed orders from Alpaca API"""
    try:
        logger.info("📊 Fetching orders from Alpaca...")
        url = f"{ALPACA_BASE_URL}/v2/orders"
        headers = get_alpaca_headers()

        # Get all filled orders (limit to 500 most recent)
        params = {
            'status': 'closed',  # Only closed/filled orders
            'limit': 500,
            'direction': 'desc'  # Most recent first
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        orders = response.json()
        if isinstance(orders, list):
            logger.info(f"✅ Retrieved {len(orders)} orders from Alpaca")
        else:
            logger.warn(f"⚠️  Unexpected orders response format: {type(orders)}")
            return []

        return orders
    except requests.RequestException as e:
        logger.error(f"❌ Failed to fetch orders: {e}")
        return []

def calculate_daily_performance(account_info):
    """Calculate daily performance metrics - REAL DATA ONLY"""
    if not account_info:
        return None

    try:
        # CRITICAL: No fake 0 defaults for portfolio metrics
        portfolio_value = account_info.get('portfolio_value')
        if portfolio_value is None:
            logger.warning("⚠️  portfolio_value not available from Alpaca")
            return None
        portfolio_value = float(portfolio_value)

        last_equity = account_info.get('last_equity')  # NO FALLBACK - return None if missing
        cash = account_info.get('cash')
        if cash is None:
            logger.warning("⚠️  cash balance not available from Alpaca")
            return None
        cash = float(cash)

        # REAL DATA ONLY: Only calculate daily P&L if we have previous equity value
        if last_equity is None:
            logger.warning("⚠️  last_equity not available from Alpaca - cannot calculate daily P&L")
            return None

        last_equity = float(last_equity)
        if last_equity <= 0:
            logger.warning("⚠️  last_equity is invalid (<=0) - cannot calculate daily P&L")
            return None

        # Calculate daily P&L from real data
        daily_pnl = portfolio_value - last_equity
        daily_pnl_percent = (daily_pnl / last_equity * 100) if last_equity > 0 else None

        # Total return: calculate from portfolio value change only if we have valid baseline
        total_return_percent = None
        if portfolio_value > 0 and last_equity > 0:
            # Use previous equity as baseline for return calculation
            total_return_percent = ((portfolio_value - last_equity) / last_equity * 100)

        return {
            'portfolio_value': portfolio_value,
            'daily_pnl': daily_pnl if daily_pnl != 0 else None,  # Return None instead of 0 if no change
            'daily_pnl_percent': daily_pnl_percent,
            'total_return_percent': total_return_percent,
            'cash': cash
        }
    except (KeyError, ValueError, TypeError) as e:
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
                quantity DOUBLE PRECISION,
                average_cost DOUBLE PRECISION,
                current_price DOUBLE PRECISION,
                market_value DOUBLE PRECISION,
                unrealized_pnl DOUBLE PRECISION,
                cost_basis DOUBLE PRECISION,
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
                user_id VARCHAR(255) NOT NULL,
                date DATE NOT NULL,
                total_value DECIMAL(15, 2),
                daily_pnl DECIMAL(15, 2),
                daily_pnl_percent DECIMAL(8, 4),
                total_pnl DECIMAL(15, 2),
                total_pnl_percent DECIMAL(8, 4),
                daily_return DECIMAL(8, 4),
                total_return DECIMAL(8, 4),
                max_drawdown DECIMAL(8, 4),
                volatility DECIMAL(8, 4),
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
    user_id = PORTFOLIO_USER_ID  # Real user account ID from environment

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
            qty_raw = position.get('qty')
            current_price_raw = position.get('current_price')
            avg_cost_raw = position.get('avg_fill_price')
            market_value_raw = position.get('market_value')
            unrealized_gain_raw = position.get('unrealized_gain')
            unrealized_gain_pct_raw = position.get('unrealized_gain_pct')

            # CRITICAL: Skip if any essential data missing (no fake 0 defaults for portfolio data)
            if None in [qty_raw, current_price_raw, avg_cost_raw, market_value_raw]:
                logger.warning(f"⚠️  Skipping {symbol}: missing critical position data from Alpaca")
                continue

            qty = float(qty_raw)
            # Skip closed/zero positions
            if qty == 0 or qty < 0.0001:
                continue

            current_price = float(current_price_raw)
            avg_cost = float(avg_cost_raw)
            market_value = float(market_value_raw)
            unrealized_gain = float(unrealized_gain_raw) if unrealized_gain_raw is not None else None
            unrealized_gain_pct = (float(unrealized_gain_pct_raw) * 100) if unrealized_gain_pct_raw is not None else None

            # Get sector from asset info
            sector = position.get('asset', {}).get('sector', 'Other') if isinstance(position.get('asset'), dict) else 'Other'

            cur.execute("""
                INSERT INTO portfolio_holdings
                (user_id, symbol, quantity, current_price, average_cost, market_value, unrealized_gain, unrealized_gain_pct, sector)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    current_price = EXCLUDED.current_price,
                    average_cost = EXCLUDED.average_cost,
                    market_value = EXCLUDED.market_value,
                    unrealized_gain = EXCLUDED.unrealized_gain,
                    unrealized_gain_pct = EXCLUDED.unrealized_gain_pct,
                    sector = EXCLUDED.sector,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                user_id, symbol, qty, current_price, avg_cost, market_value, unrealized_gain, unrealized_gain_pct, sector
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

def load_trades(conn, orders):
    """Load Alpaca trade orders into database"""
    cur = conn.cursor()

    if not orders:
        logger.info("ℹ️  No orders to load")
        return 0

    loaded_count = 0

    for order in orders:
        try:
            symbol = order.get('symbol')
            side = order.get('side', '').lower()  # 'buy' or 'sell'

            # Skip orders without critical data
            if not symbol:
                logger.debug(f"⚠️  Skipping order: missing symbol")
                continue

            # Only load filled orders - REAL DATA ONLY
            filled_qty = order.get('filled_qty')

            # Skip if not filled or no filled quantity
            if filled_qty is None or float(filled_qty) == 0:
                logger.debug(f"⚠️  Skipping {symbol} order: not filled")
                continue

            filled_qty = float(filled_qty)

            # Get filled price - use filled_avg_price for actual execution price
            filled_avg_price = order.get('filled_avg_price')
            if filled_avg_price is None:
                # Fallback to limit_price if avg_price not available
                filled_avg_price = order.get('limit_price')

            if filled_avg_price is None:
                logger.debug(f"⚠️  Skipping {symbol} order: no price data")
                continue

            filled_avg_price = float(filled_avg_price)

            # Get filled timestamp
            filled_at = order.get('filled_at')
            if not filled_at:
                logger.debug(f"⚠️  Skipping {symbol} order: no fill timestamp")
                continue

            # Calculate total amount (order_value in schema)
            total_amount = filled_qty * filled_avg_price

            # Get commission if available (else default to 0)
            commission = float(order.get('commission', 0)) if order.get('commission') else 0

            # Insert into trades table - using actual database schema
            # Columns: symbol, type (buy/sell), quantity, execution_price, execution_date, order_value, commission
            cur.execute("""
                INSERT INTO trades
                (symbol, type, quantity, execution_price, execution_date, order_value, commission)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol,                      # symbol
                side,                        # type (buy/sell)
                filled_qty,                  # quantity
                filled_avg_price,            # execution_price
                filled_at,                   # execution_date (actual fill time)
                total_amount,                # order_value
                commission                   # commission
            ))

            loaded_count += 1
            logger.debug(f"  ✓ Loaded trade: {symbol} {side} {filled_qty}@${filled_avg_price:.2f}")

        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"⚠️  Failed to process order: {e}")
            continue

    try:
        conn.commit()
        logger.info(f"✅ Loaded {loaded_count} trades into database")
        return loaded_count
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to commit trades: {e}")
        conn.rollback()
        raise

def load_performance(conn, account_info):
    """Load portfolio performance into database - REAL DATA ONLY"""
    cur = conn.cursor()
    user_id = PORTFOLIO_USER_ID  # Real user account ID from environment

    perf = calculate_daily_performance(account_info)
    if not perf:
        logger.info("ℹ️  Skipping performance update - insufficient real data from Alpaca")
        logger.info("   (Alpaca account may not have last_equity data available yet)")
        return

    try:
        # Only insert values that are real data - NO FALLBACK defaults
        cur.execute("""
            INSERT INTO portfolio_performance
            (user_id, date, total_value, daily_pnl, daily_pnl_percent, total_pnl_percent, created_at)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, date) DO UPDATE SET
                total_value = EXCLUDED.total_value,
                daily_pnl = EXCLUDED.daily_pnl,
                daily_pnl_percent = EXCLUDED.daily_pnl_percent,
                total_pnl_percent = EXCLUDED.total_pnl_percent,
                created_at = EXCLUDED.created_at
        """, (
            user_id,
            perf['portfolio_value'],
            perf['daily_pnl'],
            perf['daily_pnl_percent'],
            perf['total_return_percent']
        ))

        conn.commit()
        daily_pnl = perf['daily_pnl'] if perf['daily_pnl'] is not None else "N/A"
        daily_pct = f"{perf['daily_pnl_percent']:.2f}%" if perf['daily_pnl_percent'] is not None else "N/A"
        logger.info(f"✅ Loaded performance data - Portfolio: ${perf['portfolio_value']:,.2f}, Daily P&L: {daily_pnl} ({daily_pct})")
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to load performance: {e}")
        conn.rollback()
        raise

def load_historical_performance(conn, portfolio_history):
    """Load historical portfolio performance from Alpaca into database"""
    cur = conn.cursor()
    user_id = PORTFOLIO_USER_ID  # Real user account ID from environment

    if not portfolio_history or 'equity' not in portfolio_history:
        logger.warn("⚠️  No historical equity data available")
        return 0

    try:
        timestamps = portfolio_history.get('timestamp', [])
        equity_values = portfolio_history.get('equity', [])

        if not timestamps or not equity_values:
            logger.warn("⚠️  Empty portfolio history data")
            return 0

        # Clear existing performance data to start fresh
        try:
            cur.execute("DELETE FROM portfolio_performance WHERE user_id = %s", (user_id,))
            logger.info("🗑️  Cleared previous performance history")
        except psycopg2.Error as e:
            logger.warn(f"Could not clear performance data: {e}")

        loaded_count = 0
        previous_value = None
        first_value = None

        # Convert and validate equity values
        valid_equities = []
        valid_timestamps = []
        for ts, eq in zip(timestamps, equity_values):
            try:
                equity = float(eq)
                if equity > 0:  # REAL DATA ONLY - ignore zero or negative values
                    valid_equities.append(equity)
                    valid_timestamps.append(ts)
            except (ValueError, TypeError):
                continue

        if not valid_equities:
            logger.warn("⚠️  No valid equity data in portfolio history")
            return 0

        first_value = valid_equities[0]

        for timestamp, equity in zip(valid_timestamps, valid_equities):
            try:
                # Parse timestamp (Unix timestamp in seconds)
                if isinstance(timestamp, (int, float)):
                    perf_date = datetime.fromtimestamp(timestamp).date()
                else:
                    perf_date = datetime.fromisoformat(str(timestamp)).date()

                # Calculate daily P&L - REAL DATA ONLY
                daily_pnl = None
                daily_pnl_percent = None

                if previous_value is not None and previous_value > 0:
                    daily_pnl = equity - previous_value
                    daily_pnl_percent = (daily_pnl / previous_value) * 100

                previous_value = equity

                # Calculate total P&L from first value
                total_pnl_percent = None
                if first_value is not None and first_value > 0:
                    total_pnl_percent = ((equity - first_value) / first_value) * 100

                # Insert into database - only real data
                cur.execute("""
                    INSERT INTO portfolio_performance
                    (user_id, date, total_value, daily_pnl, daily_pnl_percent, total_pnl_percent, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, date) DO UPDATE SET
                        total_value = EXCLUDED.total_value,
                        daily_pnl = EXCLUDED.daily_pnl,
                        daily_pnl_percent = EXCLUDED.daily_pnl_percent,
                        total_pnl_percent = EXCLUDED.total_pnl_percent,
                        created_at = EXCLUDED.created_at
                """, (
                    user_id,
                    perf_date,
                    round(equity, 2),
                    round(daily_pnl, 2) if daily_pnl is not None else None,
                    round(daily_pnl_percent, 4) if daily_pnl_percent is not None else None,
                    round(total_pnl_percent, 4) if total_pnl_percent is not None else None
                ))

                loaded_count += 1

                # Log progress every 50 entries
                if loaded_count % 50 == 0:
                    logger.info(f"  ✓ Loaded {loaded_count} historical records... Latest: {perf_date} - ${equity:,.2f}")

            except (ValueError, TypeError) as e:
                logger.debug(f"⚠️  Could not process history entry: {e}")
                continue

        if loaded_count > 0:
            conn.commit()
            logger.info(f"✅ Loaded {loaded_count} days of Alpaca portfolio history")
        else:
            logger.warn("⚠️  No historical records loaded")

        return loaded_count

    except Exception as e:
        logger.error(f"❌ Failed to load historical performance: {e}")
        conn.rollback()
        return 0

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
        logger.info("📊 Phase 1: Fetching current holdings and account data...")
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

        # Fetch and load trades and historical performance data
        logger.info("")
        logger.info("📈 Phase 2: Fetching trade history and portfolio performance...")

        # Fetch orders from Alpaca
        orders = fetch_orders()
        trade_count = 0
        if orders:
            trade_count = load_trades(conn, orders)

        # Fetch historical portfolio performance
        portfolio_history = fetch_account_equity_history()

        if portfolio_history:
            history_count = load_historical_performance(conn, portfolio_history)
            logger.info(f"✅ Successfully loaded {history_count} historical data points")
        else:
            logger.warn("⚠️  Could not fetch portfolio history - dashboard metrics may be limited")
            logger.info("   This is normal if account has limited trading history")

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Alpaca Portfolio Data Loader Complete")
        logger.info("=" * 60)
        logger.info("")
        logger.info("📊 Dashboard Status:")
        logger.info(f"   ✓ Holdings: {'Loaded' if positions else 'Empty'}")
        logger.info(f"   ✓ Current Performance: {'Loaded' if account else 'Failed'}")
        logger.info(f"   ✓ Trade History: {trade_count} trades loaded" if trade_count > 0 else "   ✓ Trade History: No trades found")
        logger.info(f"   ✓ Historical Data: {'Available for metrics' if portfolio_history and history_count > 10 else 'Limited'}")
        logger.info("")
        logger.info("💡 Refresh your portfolio dashboard and trade history to see all data")
        return True

    except Exception as e:
        logger.error(f"❌ Loader failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
