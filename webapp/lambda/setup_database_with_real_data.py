#!/usr/bin/env python3
"""
Database setup script with real yfinance data
Creates database, tables, and populates with real market data
"""

import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection parameters
DB_PARAMS = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',  # Use postgres user for setup
    'dbname': 'postgres',  # Connect to postgres db for setup
}

def create_database_and_user():
    """Create the stocks database and user if they don't exist."""
    try:
        # Connect as postgres user to create database and user
        conn = psycopg2.connect(**DB_PARAMS)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # Create user if not exists
        try:
            cur.execute("CREATE USER stocks WITH PASSWORD 'stocks';")
            logger.info("✅ Created user 'stocks'")
        except psycopg2.Error as e:
            if "already exists" in str(e):
                logger.info("ℹ️ User 'stocks' already exists")
            else:
                logger.error(f"Error creating user: {e}")
        
        # Create database if not exists
        try:
            cur.execute("CREATE DATABASE stocks OWNER stocks;")
            logger.info("✅ Created database 'stocks'")
        except psycopg2.Error as e:
            if "already exists" in str(e):
                logger.info("ℹ️ Database 'stocks' already exists")
            else:
                logger.error(f"Error creating database: {e}")
        
        # Grant privileges
        cur.execute("GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;")
        logger.info("✅ Granted privileges to stocks user")
        
        cur.close()
        conn.close()
        
        return True
        
    except psycopg2.Error as e:
        logger.error(f"❌ Database setup failed: {e}")
        return False

def get_stocks_connection():
    """Get connection to stocks database."""
    try:
        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            user='stocks',
            password='stocks',
            dbname='stocks'
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"❌ Failed to connect to stocks database: {e}")
        return None

def create_tables(conn):
    """Create all required tables matching the application schema."""
    tables_sql = """
    -- Create stock_symbols table
    CREATE TABLE IF NOT EXISTS stock_symbols (
        symbol VARCHAR(50) PRIMARY KEY,
        name TEXT,
        exchange VARCHAR(100),
        security_name TEXT,
        cqs_symbol VARCHAR(50),
        market_category VARCHAR(50),
        test_issue CHAR(1),
        financial_status VARCHAR(50),
        round_lot_size INT,
        etf CHAR(1),
        secondary_symbol VARCHAR(50)
    );
    
    -- Create price_daily table (matching yfinance structure)
    CREATE TABLE IF NOT EXISTS price_daily (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open_price DOUBLE PRECISION,
        high_price DOUBLE PRECISION,
        low_price DOUBLE PRECISION,
        close_price DOUBLE PRECISION,
        adj_close_price DOUBLE PRECISION,
        volume BIGINT,
        change_amount DOUBLE PRECISION,
        change_percent DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(symbol, date)
    );
    
    -- Create technical_data_daily table
    CREATE TABLE IF NOT EXISTS technical_data_daily (
        symbol VARCHAR(50),
        date TIMESTAMP,
        rsi DOUBLE PRECISION,
        macd DOUBLE PRECISION,
        macd_signal DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        mom DOUBLE PRECISION,
        roc DOUBLE PRECISION,
        adx DOUBLE PRECISION,
        plus_di DOUBLE PRECISION,
        minus_di DOUBLE PRECISION,
        atr DOUBLE PRECISION,
        ad DOUBLE PRECISION,
        cmf DOUBLE PRECISION,
        mfi DOUBLE PRECISION,
        td_sequential DOUBLE PRECISION,
        td_combo DOUBLE PRECISION,
        marketwatch DOUBLE PRECISION,
        dm DOUBLE PRECISION,
        sma_10 DOUBLE PRECISION,
        sma_20 DOUBLE PRECISION,
        sma_50 DOUBLE PRECISION,
        sma_150 DOUBLE PRECISION,
        sma_200 DOUBLE PRECISION,
        ema_4 DOUBLE PRECISION,
        ema_9 DOUBLE PRECISION,
        ema_21 DOUBLE PRECISION,
        bbands_lower DOUBLE PRECISION,
        bbands_middle DOUBLE PRECISION,
        bbands_upper DOUBLE PRECISION,
        bb_lower DOUBLE PRECISION,
        bb_upper DOUBLE PRECISION,
        pivot_high DOUBLE PRECISION,
        pivot_low DOUBLE PRECISION,
        pivot_high_triggered DOUBLE PRECISION,
        pivot_low_triggered DOUBLE PRECISION,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    
    -- Create stocks table
    CREATE TABLE IF NOT EXISTS stocks (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL UNIQUE,
        name VARCHAR(255),
        sector VARCHAR(100),
        industry VARCHAR(100),
        market_cap NUMERIC,
        price NUMERIC,
        dividend_yield NUMERIC,
        beta NUMERIC,
        exchange VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Create analyst_recommendations table
    CREATE TABLE IF NOT EXISTS analyst_recommendations (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        analyst_firm VARCHAR(100),
        rating VARCHAR(20),
        target_price DOUBLE PRECISION,
        current_price DOUBLE PRECISION,
        date_published DATE,
        date_updated DATE DEFAULT CURRENT_DATE,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Create portfolio_holdings table
    CREATE TABLE IF NOT EXISTS portfolio_holdings (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity NUMERIC NOT NULL DEFAULT 0,
        average_cost NUMERIC NOT NULL DEFAULT 0,
        current_price NUMERIC DEFAULT 0,
        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, symbol)
    );
    
    -- Create portfolio_performance table
    CREATE TABLE IF NOT EXISTS portfolio_performance (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        date DATE NOT NULL,
        total_value NUMERIC NOT NULL DEFAULT 0,
        daily_pnl NUMERIC DEFAULT 0,
        total_pnl NUMERIC DEFAULT 0,
        total_pnl_percent NUMERIC DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, date)
    );
    
    -- Create economic_data table
    CREATE TABLE IF NOT EXISTS economic_data (
        series_id TEXT NOT NULL,
        date DATE NOT NULL,
        value DOUBLE PRECISION,
        title TEXT,
        units TEXT,
        frequency TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (series_id, date)
    );
    
    -- Grant permissions to stocks user
    GRANT ALL ON SCHEMA public TO stocks;
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stocks;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stocks;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stocks;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stocks;
    """
    
    try:
        cur = conn.cursor()
        cur.execute(tables_sql)
        conn.commit()
        cur.close()
        logger.info("✅ Created all database tables")
        return True
    except psycopg2.Error as e:
        logger.error(f"❌ Error creating tables: {e}")
        conn.rollback()
        return False

def fetch_and_insert_stock_data(conn, symbols):
    """Fetch real stock data from yfinance and insert into database."""
    cur = conn.cursor()
    
    # Major stock symbols to populate
    for symbol in symbols:
        try:
            logger.info(f"📊 Fetching data for {symbol}")
            ticker = yf.Ticker(symbol)
            
            # Get stock info
            try:
                info = ticker.info
                stock_name = info.get('longName', info.get('shortName', symbol))
                sector = info.get('sector', 'Unknown')
                industry = info.get('industry', 'Unknown')
                market_cap = info.get('marketCap', 0)
                price = info.get('currentPrice', 0)
                dividend_yield = info.get('dividendYield', 0)
                beta = info.get('beta', 0)
                exchange = info.get('exchange', 'Unknown')
                
                # Insert stock info
                cur.execute("""
                    INSERT INTO stocks (symbol, name, sector, industry, market_cap, price, dividend_yield, beta, exchange)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        name = EXCLUDED.name,
                        sector = EXCLUDED.sector,
                        industry = EXCLUDED.industry,
                        market_cap = EXCLUDED.market_cap,
                        price = EXCLUDED.price,
                        dividend_yield = EXCLUDED.dividend_yield,
                        beta = EXCLUDED.beta,
                        exchange = EXCLUDED.exchange,
                        updated_at = CURRENT_TIMESTAMP
                """, (symbol, stock_name, sector, industry, market_cap, price, dividend_yield, beta, exchange))
                
                # Insert stock symbol info
                cur.execute("""
                    INSERT INTO stock_symbols (symbol, name, exchange)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                        name = EXCLUDED.name,
                        exchange = EXCLUDED.exchange
                """, (symbol, stock_name, exchange))
                
                logger.info(f"✅ Inserted stock info for {symbol}")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not get info for {symbol}: {e}")
            
            # Get historical price data (last 30 days)
            try:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                hist = ticker.history(start=start_date, end=end_date)
                
                for date, row in hist.iterrows():
                    date_str = date.strftime('%Y-%m-%d')
                    
                    # Calculate change
                    change_amount = 0
                    change_percent = 0
                    if len(hist) > 1:
                        prev_close = hist['Close'].shift(1).loc[date]
                        if pd.notna(prev_close) and prev_close != 0:
                            change_amount = row['Close'] - prev_close
                            change_percent = (change_amount / prev_close) * 100
                    
                    cur.execute("""
                        INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, adj_close_price, volume, change_amount, change_percent)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            open_price = EXCLUDED.open_price,
                            high_price = EXCLUDED.high_price,
                            low_price = EXCLUDED.low_price,
                            close_price = EXCLUDED.close_price,
                            adj_close_price = EXCLUDED.adj_close_price,
                            volume = EXCLUDED.volume,
                            change_amount = EXCLUDED.change_amount,
                            change_percent = EXCLUDED.change_percent
                    """, (symbol, date_str, float(row['Open']), float(row['High']), float(row['Low']), 
                         float(row['Close']), float(row['Close']), int(row['Volume']), change_amount, change_percent))
                
                logger.info(f"✅ Inserted {len(hist)} price records for {symbol}")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not get price data for {symbol}: {e}")
                
        except Exception as e:
            logger.error(f"❌ Error processing {symbol}: {e}")
            
        # Commit after each symbol to avoid losing data
        conn.commit()
    
    cur.close()

def insert_analyst_data(conn):
    """Insert sample analyst recommendation data."""
    analyst_data = [
        ('AAPL', 'Goldman Sachs', 'BUY', 200.00, 186.75, '2024-01-01'),
        ('AAPL', 'Morgan Stanley', 'OVERWEIGHT', 195.00, 186.75, '2024-01-02'),
        ('MSFT', 'JP Morgan', 'OVERWEIGHT', 450.00, 411.25, '2024-01-01'),
        ('GOOGL', 'Barclays', 'EQUAL WEIGHT', 145.00, 139.20, '2024-01-01'),
        ('TSLA', 'Wedbush', 'OUTPERFORM', 300.00, 250.85, '2024-01-01'),
        ('NVDA', 'Bank of America', 'BUY', 950.00, 878.90, '2024-01-01'),
    ]
    
    cur = conn.cursor()
    for data in analyst_data:
        try:
            cur.execute("""
                INSERT INTO analyst_recommendations (symbol, analyst_firm, rating, target_price, current_price, date_published)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, data)
        except psycopg2.Error as e:
            logger.warning(f"⚠️ Error inserting analyst data: {e}")
    
    conn.commit()
    cur.close()
    logger.info("✅ Inserted analyst recommendation data")

def insert_portfolio_data(conn):
    """Insert sample portfolio data for testing."""
    portfolio_data = [
        ('dev-user-bypass', 'AAPL', 100, 150.00, 186.75),
        ('dev-user-bypass', 'MSFT', 50, 380.00, 411.25),
        ('dev-user-bypass', 'GOOGL', 75, 120.00, 139.20),
        ('dev-user-bypass', 'TSLA', 25, 220.00, 250.85),
        ('dev-user-bypass', 'NVDA', 10, 800.00, 878.90),
        ('demo_user', 'AAPL', 50, 160.00, 186.75),
        ('demo_user', 'MSFT', 25, 400.00, 411.25),
    ]
    
    cur = conn.cursor()
    for user_id, symbol, quantity, avg_cost, current_price in portfolio_data:
        try:
            cur.execute("""
                INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, symbol) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    average_cost = EXCLUDED.average_cost,
                    current_price = EXCLUDED.current_price
            """, (user_id, symbol, quantity, avg_cost, current_price))
        except psycopg2.Error as e:
            logger.warning(f"⚠️ Error inserting portfolio data: {e}")
    
    conn.commit()
    cur.close()
    logger.info("✅ Inserted portfolio holdings data")

def main():
    """Main setup function."""
    logger.info("🚀 Starting database setup with real yfinance data...")
    
    # Major stock symbols to populate
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'JPM', 'JNJ', 'V', 'SPY', 'QQQ']
    
    # Step 1: Create database and user
    if not create_database_and_user():
        logger.error("❌ Failed to create database and user")
        sys.exit(1)
    
    # Step 2: Connect to stocks database
    conn = get_stocks_connection()
    if not conn:
        logger.error("❌ Failed to connect to stocks database")
        sys.exit(1)
    
    try:
        # Step 3: Create tables
        if not create_tables(conn):
            logger.error("❌ Failed to create tables")
            sys.exit(1)
        
        # Step 4: Fetch and insert real stock data
        logger.info("📈 Fetching real market data from yfinance...")
        fetch_and_insert_stock_data(conn, symbols)
        
        # Step 5: Insert analyst data
        insert_analyst_data(conn)
        
        # Step 6: Insert portfolio data
        insert_portfolio_data(conn)
        
        # Step 7: Verify data
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stocks")
        stock_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM price_daily")
        price_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM analyst_recommendations")
        analyst_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM portfolio_holdings")
        portfolio_count = cur.fetchone()[0]
        cur.close()
        
        logger.info(f"""
✅ Database setup completed successfully!
📊 Data summary:
   - Stocks: {stock_count}
   - Price records: {price_count}
   - Analyst recommendations: {analyst_count}
   - Portfolio holdings: {portfolio_count}

🔗 Connection details:
   Host: localhost
   Port: 5432
   Database: stocks
   Username: stocks
   Password: stocks

🌍 Environment variables:
   export DB_HOST=localhost
   export DB_PORT=5432
   export DB_USER=stocks
   export DB_PASSWORD=stocks
   export DB_NAME=stocks
   export DB_SSL=false
        """)
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()