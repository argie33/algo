#!/usr/bin/env python3
"""
Database Initialization Script
Creates all database tables needed for the financial dashboard
"""
import os
import sys
import json
import logging
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Fetch database credentials from AWS Secrets Manager."""
    logger.info("Fetching database credentials from Secrets Manager")
    
    try:
        secret_arn = os.environ.get('DB_SECRET_ARN')
        if not secret_arn:
            raise ValueError("DB_SECRET_ARN environment variable not set")
            
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': int(secret.get('port', 5432)),
            'database': secret.get('dbname', 'stocks'),
            'user': secret['username'],
            'password': secret['password'],
            'sslmode': 'require'
        }
    except Exception as e:
        logger.error(f"Failed to get database credentials: {e}")
        raise

def create_all_tables(cursor, conn):
    """Create all database tables"""
    logger.info("Creating all database tables")
    
    tables = [
        # Core user tables
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP
        )
        """,
        
        # API keys table
        """
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
        )
        """,
        
        # Portfolio tables
        """
        CREATE TABLE IF NOT EXISTS portfolio_metadata (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
        """,
        
        """
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            portfolio_id INTEGER REFERENCES portfolio_metadata(id) ON DELETE CASCADE,
            symbol VARCHAR(10) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            avg_cost DECIMAL(10, 2) NOT NULL,
            purchase_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # Stock symbols table
        """
        CREATE TABLE IF NOT EXISTS stock_symbols (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            ipo_year INTEGER,
            exchange VARCHAR(10),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        
        # Health monitoring table
        """
        CREATE TABLE IF NOT EXISTS health_status (
            id SERIAL PRIMARY KEY,
            table_name VARCHAR(100) UNIQUE NOT NULL,
            status VARCHAR(20) NOT NULL,
            record_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP,
            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_stale BOOLEAN DEFAULT FALSE,
            error TEXT,
            table_category VARCHAR(50),
            critical_table BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    ]
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_portfolio_id ON portfolio_holdings(portfolio_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_stock_symbols_sector ON stock_symbols(sector)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_table_name ON health_status(table_name)"
    ]
    
    try:
        # Create tables
        for i, table_sql in enumerate(tables):
            cursor.execute(table_sql)
            logger.info(f"Created table {i+1}/{len(tables)}")
        
        # Create indexes
        for i, index_sql in enumerate(indexes):
            cursor.execute(index_sql)
            logger.info(f"Created index {i+1}/{len(indexes)}")
        
        # Create update trigger function
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ language 'plpgsql'
        """)
        
        # Create triggers for updated_at columns
        triggers = [
            "CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_user_api_keys_updated_at BEFORE UPDATE ON user_api_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_metadata_updated_at BEFORE UPDATE ON portfolio_metadata FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_stock_symbols_updated_at BEFORE UPDATE ON stock_symbols FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_health_status_updated_at BEFORE UPDATE ON health_status FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        ]
        
        for trigger_sql in triggers:
            cursor.execute(f"{trigger_sql.replace('CREATE TRIGGER', 'CREATE TRIGGER IF NOT EXISTS')}")
        
        conn.commit()
        logger.info("All tables, indexes, and triggers created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        return False

def main():
    """Main function to initialize database"""
    logger.info("Starting database initialization")
    
    try:
        # Get database configuration
        db_config = get_db_config()
        
        # Connect to database
        logger.info(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        # Create all tables
        if create_all_tables(cursor, conn):
            logger.info("Database initialization completed successfully")
            success = True
        else:
            logger.error("Database initialization failed")
            success = False
        
        # Close connection
        cursor.close()
        conn.close()
        
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())