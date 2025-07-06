#!/usr/bin/env python3
"""
Initialize Portfolio and API Keys Tables
Creates necessary tables for portfolio management and API key storage
"""

import sys
import os
import json
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    try:
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        secret_json = json.loads(secret_str)
        return {
            "host": secret_json["host"],
            "port": secret_json.get("port", 5432),
            "user": secret_json["username"],
            "password": secret_json["password"],
            "dbname": secret_json["dbname"]
        }
    except Exception as e:
        logger.error(f"Failed to get database config: {e}")
        return None

def create_portfolio_tables(cur, conn):
    """Create portfolio and API keys tables"""
    
    # Create user_api_keys table
    logger.info("Creating user_api_keys table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_api_keys (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            provider VARCHAR(50) NOT NULL,
            encrypted_api_key TEXT NOT NULL,
            key_iv VARCHAR(32) NOT NULL,
            key_auth_tag VARCHAR(32) NOT NULL,
            encrypted_api_secret TEXT,
            secret_iv VARCHAR(32),
            secret_auth_tag VARCHAR(32),
            user_salt VARCHAR(32) NOT NULL,
            is_sandbox BOOLEAN DEFAULT true,
            is_active BOOLEAN DEFAULT true,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            UNIQUE(user_id, provider)
        );
    """)
    
    # Create indexes for user_api_keys
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);")
    
    # Create portfolio_holdings table (if not exists)
    logger.info("Creating portfolio_holdings table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            quantity DECIMAL(15,4) NOT NULL,
            market_value DECIMAL(15,2),
            cost_basis DECIMAL(15,2),
            pnl DECIMAL(15,2),
            pnl_percent DECIMAL(8,4),
            weight DECIMAL(8,4),
            sector VARCHAR(100),
            current_price DECIMAL(12,4),
            average_entry_price DECIMAL(12,4),
            day_change DECIMAL(15,2),
            day_change_percent DECIMAL(8,4),
            exchange VARCHAR(20),
            broker VARCHAR(50),
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, symbol, broker)
        );
    """)
    
    # Create portfolio_metadata table
    logger.info("Creating portfolio_metadata table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_metadata (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            broker VARCHAR(50) NOT NULL,
            total_value DECIMAL(15,2),
            total_cash DECIMAL(15,2),
            total_pnl DECIMAL(15,2),
            total_pnl_percent DECIMAL(8,4),
            positions_count INTEGER,
            account_status VARCHAR(50),
            environment VARCHAR(20),
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, broker)
        );
    """)
    
    # Create indexes for portfolio tables
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id);")
    
    # Create trading_alerts table for HFT system
    logger.info("Creating trading_alerts table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trading_alerts (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            alert_type VARCHAR(50) NOT NULL, -- 'price_above', 'price_below', 'volume_surge', 'pattern'
            target_value DECIMAL(12,4),
            current_value DECIMAL(12,4),
            condition_met BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            message TEXT,
            triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active);")
    
    conn.commit()
    logger.info("All portfolio and API keys tables created successfully!")

def main():
    """Main function"""
    try:
        # Get database configuration
        config = get_db_config()
        if not config:
            logger.error("Failed to get database configuration")
            sys.exit(1)
        
        # Connect to database
        logger.info("Connecting to database...")
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            dbname=config["dbname"]
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Create tables
        create_portfolio_tables(cur, conn)
        
        # Record in last_updated table
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES ('init_portfolio_tables.py', NOW())
            ON CONFLICT (script_name) DO UPDATE
                SET last_run = EXCLUDED.last_run;
        """)
        conn.commit()
        
        logger.info("Portfolio tables initialization completed successfully!")
        
        # Close connection
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Failed to initialize portfolio tables: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()