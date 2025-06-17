#!/usr/bin/env python3
"""
Quick setup script for local testing of pivot data loading
This script will help you set up local database and test the pivot loading
"""

import psycopg2
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres", 
    "password": "password",
    "dbname": "stocks"
}

def test_database_connection():
    """Test if we can connect to the local database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()
        logging.info(f"✅ Database connection successful: {version[0]}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ Database connection failed: {e}")
        return False

def create_tables_if_needed():
    """Create the necessary tables if they don't exist"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        # Create stock_symbols table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_symbols (
                symbol VARCHAR(10) PRIMARY KEY,
                security_name VARCHAR(500),
                exchange VARCHAR(10),
                market_category VARCHAR(2),
                cqs_symbol VARCHAR(10),
                nasdaq_symbol VARCHAR(10),
                financial_status VARCHAR(1),
                etf VARCHAR(1),
                round_lot_size INTEGER,
                test_issue VARCHAR(1),
                secondary_symbol VARCHAR(10)
            );
        """)
        
        # Create price_daily table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_daily (
                symbol VARCHAR(10),
                date DATE,
                open DECIMAL(12,4),
                high DECIMAL(12,4),
                low DECIMAL(12,4),
                close DECIMAL(12,4),
                adj_close DECIMAL(12,4),
                volume BIGINT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            );
        """)
        
        # Create technical_data_daily table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS technical_data_daily (
                symbol VARCHAR(10),
                date DATE,
                rsi DECIMAL(8,4),
                macd DECIMAL(8,4),
                macd_signal DECIMAL(8,4),
                macd_hist DECIMAL(8,4),
                mom DECIMAL(8,4),
                roc DECIMAL(8,4),
                adx DECIMAL(8,4),
                atr DECIMAL(8,4),
                ad DECIMAL(15,4),
                cmf DECIMAL(8,4),
                mfi DECIMAL(8,4),
                td_sequential INTEGER,
                td_combo INTEGER,
                marketwatch DECIMAL(8,4),
                dm DECIMAL(8,4),
                sma_10 DECIMAL(12,4),
                sma_20 DECIMAL(12,4),
                sma_50 DECIMAL(12,4),
                sma_150 DECIMAL(12,4),
                sma_200 DECIMAL(12,4),
                ema_4 DECIMAL(12,4),
                ema_9 DECIMAL(12,4),
                ema_21 DECIMAL(12,4),
                bbands_lower DECIMAL(12,4),
                bbands_middle DECIMAL(12,4),
                bbands_upper DECIMAL(12,4),
                pivot_high DECIMAL(12,4),
                pivot_low DECIMAL(12,4),
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, date)
            );
        """)
        
        # Insert a few test symbols
        test_symbols = [
            ('AAPL', 'Apple Inc', 'NASDAQ', 'Q', 'AAPL', 'AAPL', 'N', 'N', 100, 'N', ''),
            ('TSLA', 'Tesla Inc', 'NASDAQ', 'Q', 'TSLA', 'TSLA', 'N', 'N', 100, 'N', ''),
            ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'Q', 'MSFT', 'MSFT', 'N', 'N', 100, 'N', '')
        ]
        
        cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE symbol IN ('AAPL', 'TSLA', 'MSFT')")
        existing_count = cur.fetchone()[0]
        
        if existing_count < 3:
            cur.executemany("""
                INSERT INTO stock_symbols 
                (symbol, security_name, exchange, market_category, cqs_symbol, nasdaq_symbol, 
                 financial_status, etf, round_lot_size, test_issue, secondary_symbol)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO NOTHING
            """, test_symbols)
            logging.info("✅ Test symbols inserted")
        
        conn.commit()
        cur.close()
        conn.close()
        
        logging.info("✅ Tables created successfully")
        return True
        
    except Exception as e:
        logging.error(f"❌ Table creation failed: {e}")
        return False

def main():
    """Main setup function"""
    logging.info("🚀 Starting local database setup for pivot testing...")
    
    # Test connection
    if not test_database_connection():
        logging.error("❌ Cannot connect to database. Please ensure:")
        logging.error("   1. PostgreSQL is running on localhost:5432")
        logging.error("   2. Database 'stocks' exists")
        logging.error("   3. User 'postgres' with password 'password' has access")
        return False
    
    # Create tables
    if not create_tables_if_needed():
        logging.error("❌ Failed to create tables")
        return False
    
    logging.info("✅ Local database setup complete!")
    logging.info("📋 Next steps:")
    logging.info("   1. Run: python loadpricedaily_local.py --symbol AAPL --limit 100")
    logging.info("   2. Run: python loadtechnicalsdaily_local.py --symbol AAPL --limit 10")
    logging.info("   3. Check pivot data in technical_data_daily table")
    
    return True

if __name__ == "__main__":
    main()
