#!/usr/bin/env python3
"""
Simple database setup without external dependencies
Uses only built-in Python libraries and psycopg2
"""

import sys
import subprocess
import json
from datetime import datetime, timedelta

def setup_database():
    """Set up database using psql commands."""
    print("🚀 Setting up stocks database...")
    
    # Commands to run as postgres user
    commands = [
        # Create user and database
        """psql -U postgres -c "CREATE USER IF NOT EXISTS stocks WITH PASSWORD 'stocks';" """,
        """psql -U postgres -c "CREATE DATABASE IF NOT EXISTS stocks OWNER stocks;" """,
        """psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;" """,
        
        # Connect to stocks database and create tables
        """psql -U stocks -d stocks -c "
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
        
        -- Create price_daily table
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
        
        -- Grant permissions
        GRANT ALL ON SCHEMA public TO stocks;
        GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO stocks;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO stocks;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO stocks;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO stocks;
        " """,
        
        # Insert initial data
        """psql -U stocks -d stocks -c "
        -- Insert stock symbols
        INSERT INTO stock_symbols (symbol, name, exchange) VALUES
        ('AAPL', 'Apple Inc.', 'NASDAQ'),
        ('MSFT', 'Microsoft Corporation', 'NASDAQ'),
        ('GOOGL', 'Alphabet Inc.', 'NASDAQ'),
        ('AMZN', 'Amazon.com Inc.', 'NASDAQ'),
        ('TSLA', 'Tesla Inc.', 'NASDAQ'),
        ('META', 'Meta Platforms Inc.', 'NASDAQ'),
        ('NVDA', 'NVIDIA Corporation', 'NASDAQ'),
        ('NFLX', 'Netflix Inc.', 'NASDAQ'),
        ('JPM', 'JPMorgan Chase & Co.', 'NYSE'),
        ('JNJ', 'Johnson & Johnson', 'NYSE'),
        ('V', 'Visa Inc.', 'NYSE'),
        ('SPY', 'SPDR S&P 500 ETF Trust', 'NYSE'),
        ('QQQ', 'Invesco QQQ Trust', 'NASDAQ')
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name,
            exchange = EXCLUDED.exchange;
            
        -- Insert stocks data
        INSERT INTO stocks (symbol, name, sector, industry, market_cap, price, dividend_yield, beta, exchange) VALUES
        ('AAPL', 'Apple Inc.', 'Technology', 'Consumer Electronics', 3000000000000, 186.75, 0.52, 1.28, 'NASDAQ'),
        ('MSFT', 'Microsoft Corporation', 'Technology', 'Software', 2800000000000, 411.25, 0.68, 0.90, 'NASDAQ'),
        ('GOOGL', 'Alphabet Inc.', 'Technology', 'Internet Services', 1800000000000, 139.20, 0.00, 1.05, 'NASDAQ'),
        ('AMZN', 'Amazon.com Inc.', 'Technology', 'E-commerce', 1500000000000, 150.40, 0.00, 1.33, 'NASDAQ'),
        ('TSLA', 'Tesla Inc.', 'Automotive', 'Electric Vehicles', 800000000000, 250.85, 0.00, 2.29, 'NASDAQ'),
        ('SPY', 'SPDR S&P 500 ETF Trust', 'ETF', 'Exchange Traded Fund', 400000000000, 446.95, 1.30, 1.00, 'NYSE'),
        ('QQQ', 'Invesco QQQ Trust', 'ETF', 'Exchange Traded Fund', 200000000000, 387.30, 0.50, 1.15, 'NASDAQ'),
        ('JPM', 'JPMorgan Chase & Co.', 'Financial Services', 'Banking', 500000000000, 185.50, 2.50, 1.18, 'NYSE'),
        ('JNJ', 'Johnson & Johnson', 'Healthcare', 'Pharmaceuticals', 420000000000, 165.20, 2.90, 0.70, 'NYSE'),
        ('NVDA', 'NVIDIA Corporation', 'Technology', 'Semiconductors', 2200000000000, 878.90, 0.08, 1.68, 'NASDAQ')
        ON CONFLICT (symbol) DO UPDATE SET
            name = EXCLUDED.name,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            market_cap = EXCLUDED.market_cap,
            price = EXCLUDED.price,
            dividend_yield = EXCLUDED.dividend_yield,
            beta = EXCLUDED.beta,
            exchange = EXCLUDED.exchange,
            updated_at = CURRENT_TIMESTAMP;
            
        -- Insert price data (last 5 days)
        INSERT INTO price_daily (symbol, date, open_price, high_price, low_price, close_price, adj_close_price, volume, change_amount, change_percent) VALUES
        ('AAPL', CURRENT_DATE, 185.50, 187.20, 184.80, 186.75, 186.75, 45000000, 1.25, 0.67),
        ('AAPL', CURRENT_DATE - INTERVAL '1 day', 183.20, 185.60, 182.90, 185.50, 185.50, 42000000, 2.30, 1.26),
        ('AAPL', CURRENT_DATE - INTERVAL '2 days', 182.40, 184.10, 181.70, 183.20, 183.20, 38000000, 0.80, 0.44),
        ('MSFT', CURRENT_DATE, 410.30, 412.80, 408.50, 411.25, 411.25, 22000000, 0.95, 0.23),
        ('MSFT', CURRENT_DATE - INTERVAL '1 day', 408.75, 410.40, 407.20, 410.30, 410.30, 21500000, 1.55, 0.38),
        ('GOOGL', CURRENT_DATE, 138.45, 139.80, 137.90, 139.20, 139.20, 18000000, 0.75, 0.54),
        ('TSLA', CURRENT_DATE, 248.60, 252.30, 247.10, 250.85, 250.85, 85000000, 2.25, 0.90),
        ('NVDA', CURRENT_DATE, 875.20, 882.50, 870.40, 878.90, 878.90, 35000000, 3.70, 0.42),
        ('SPY', CURRENT_DATE, 445.20, 447.80, 444.30, 446.95, 446.95, 65000000, 1.75, 0.39),
        ('QQQ', CURRENT_DATE, 385.40, 388.60, 384.20, 387.30, 387.30, 42000000, 1.90, 0.49)
        ON CONFLICT (symbol, date) DO UPDATE SET
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            adj_close_price = EXCLUDED.adj_close_price,
            volume = EXCLUDED.volume,
            change_amount = EXCLUDED.change_amount,
            change_percent = EXCLUDED.change_percent;
            
        -- Insert technical data
        INSERT INTO technical_data_daily (symbol, date, rsi, macd, macd_signal, sma_20, sma_50, sma_200, bbands_upper, bbands_middle, bbands_lower) VALUES
        ('AAPL', CURRENT_DATE, 65.4, 2.1, 1.8, 185.20, 182.50, 175.80, 190.50, 186.75, 183.00),
        ('MSFT', CURRENT_DATE, 58.2, 5.2, 4.1, 408.90, 405.30, 395.20, 415.80, 411.25, 406.70),
        ('GOOGL', CURRENT_DATE, 52.1, -0.8, -0.5, 138.80, 140.20, 135.60, 142.30, 139.20, 136.10),
        ('TSLA', CURRENT_DATE, 72.8, 8.5, 6.2, 245.60, 240.30, 235.80, 255.20, 250.85, 246.50),
        ('NVDA', CURRENT_DATE, 68.9, 15.2, 12.8, 870.40, 850.20, 780.60, 890.30, 878.90, 867.50)
        ON CONFLICT (symbol, date) DO UPDATE SET
            rsi = EXCLUDED.rsi,
            macd = EXCLUDED.macd,
            macd_signal = EXCLUDED.macd_signal,
            sma_20 = EXCLUDED.sma_20,
            sma_50 = EXCLUDED.sma_50,
            sma_200 = EXCLUDED.sma_200,
            bbands_upper = EXCLUDED.bbands_upper,
            bbands_middle = EXCLUDED.bbands_middle,
            bbands_lower = EXCLUDED.bbands_lower;
            
        -- Insert analyst recommendations
        INSERT INTO analyst_recommendations (symbol, analyst_firm, rating, target_price, current_price, date_published) VALUES
        ('AAPL', 'Goldman Sachs', 'BUY', 200.00, 186.75, CURRENT_DATE - INTERVAL '3 days'),
        ('AAPL', 'Morgan Stanley', 'OVERWEIGHT', 195.00, 186.75, CURRENT_DATE - INTERVAL '5 days'),
        ('MSFT', 'JP Morgan', 'OVERWEIGHT', 450.00, 411.25, CURRENT_DATE - INTERVAL '2 days'),
        ('GOOGL', 'Barclays', 'EQUAL WEIGHT', 145.00, 139.20, CURRENT_DATE - INTERVAL '1 day'),
        ('TSLA', 'Wedbush', 'OUTPERFORM', 300.00, 250.85, CURRENT_DATE - INTERVAL '4 days'),
        ('NVDA', 'Bank of America', 'BUY', 950.00, 878.90, CURRENT_DATE - INTERVAL '1 day')
        ON CONFLICT DO NOTHING;
        
        -- Insert portfolio holdings
        INSERT INTO portfolio_holdings (user_id, symbol, quantity, average_cost, current_price) VALUES
        ('dev-user-bypass', 'AAPL', 100, 150.00, 186.75),
        ('dev-user-bypass', 'MSFT', 50, 380.00, 411.25),
        ('dev-user-bypass', 'GOOGL', 75, 120.00, 139.20),
        ('dev-user-bypass', 'TSLA', 25, 220.00, 250.85),
        ('dev-user-bypass', 'NVDA', 10, 800.00, 878.90),
        ('demo_user', 'AAPL', 50, 160.00, 186.75),
        ('demo_user', 'MSFT', 25, 400.00, 411.25)
        ON CONFLICT (user_id, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            average_cost = EXCLUDED.average_cost,
            current_price = EXCLUDED.current_price;
        " """
    ]
    
    success = True
    for cmd in commands:
        try:
            print(f"Running: {cmd[:50]}...")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env={'PGPASSWORD': 'stocks'})
            if result.returncode != 0:
                print(f"❌ Command failed: {result.stderr}")
                success = False
            else:
                print(f"✅ Command succeeded")
        except Exception as e:
            print(f"❌ Error running command: {e}")
            success = False
    
    return success

def test_connection():
    """Test the database connection from Node.js."""
    print("\n🔗 Testing database connection from Node.js...")
    
    env_vars = {
        'DB_HOST': 'localhost',
        'DB_PORT': '5432',
        'DB_USER': 'stocks',
        'DB_PASSWORD': 'stocks',
        'DB_NAME': 'stocks',
        'DB_SSL': 'false'
    }
    
    # Create test script
    test_script = '''
const db = require('./utils/database');

async function test() {
    try {
        console.log('🔌 Initializing database connection...');
        const pool = await db.initializeDatabase();
        
        if (!pool) {
            console.log('❌ Database connection failed');
            process.exit(1);
        }
        
        console.log('✅ Database connected successfully');
        
        // Test queries
        const dbInfo = await db.query('SELECT current_database(), current_user, now()');
        console.log('📊 Database info:', dbInfo.rows[0]);
        
        const stockCount = await db.query('SELECT COUNT(*) as count FROM stocks');
        console.log('📈 Stock count:', stockCount.rows[0].count);
        
        const priceCount = await db.query('SELECT COUNT(*) as count FROM price_daily');
        console.log('💰 Price records:', priceCount.rows[0].count);
        
        const techCount = await db.query('SELECT COUNT(*) as count FROM technical_data_daily');
        console.log('📊 Technical records:', techCount.rows[0].count);
        
        console.log('\\n✅ All database tests passed!');
        
    } catch (error) {
        console.error('❌ Database test failed:', error.message);
        process.exit(1);
    } finally {
        process.exit(0);
    }
}

test();
'''
    
    try:
        # Write test script
        with open('test_db_connection.js', 'w') as f:
            f.write(test_script)
        
        # Set environment and run test
        import os
        my_env = os.environ.copy()
        my_env.update(env_vars)
        
        result = subprocess.run(['node', 'test_db_connection.js'], 
                              capture_output=True, text=True, env=my_env)
        
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False
    finally:
        # Clean up test file
        try:
            import os
            os.remove('test_db_connection.js')
        except:
            pass

def main():
    print("🚀 Setting up stocks database with realistic test data...")
    
    # Setup database
    if not setup_database():
        print("❌ Database setup failed")
        return False
    
    # Test connection
    if not test_connection():
        print("❌ Connection test failed")
        return False
    
    print("""
✅ Database setup completed successfully!

🔗 Connection details:
   Host: localhost
   Port: 5432
   Database: stocks
   Username: stocks
   Password: stocks

🌍 Set these environment variables:
   export DB_HOST=localhost
   export DB_PORT=5432
   export DB_USER=stocks
   export DB_PASSWORD=stocks
   export DB_NAME=stocks
   export DB_SSL=false

📊 Ready to use real database functionality!
    """)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)