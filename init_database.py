#!/usr/bin/env python3
"""
Database Initialization Script
Creates all database tables needed for the financial dashboard
Updated with enhanced debugging for portfolio_id column issue
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
            user_id INTEGER NOT NULL,
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
        
        # Portfolio tables for webapp compatibility
        """
        CREATE TABLE IF NOT EXISTS portfolio_metadata (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            api_key_id INTEGER,
            total_equity DECIMAL(15, 2),
            total_market_value DECIMAL(15, 2),
            buying_power DECIMAL(15, 2),
            cash DECIMAL(15, 2),
            account_type VARCHAR(50),
            name VARCHAR(255),
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
        """,
        
        """
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            api_key_id INTEGER,
            symbol VARCHAR(20) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            avg_cost DECIMAL(10, 4),
            current_price DECIMAL(10, 4),
            market_value DECIMAL(15, 2),
            unrealized_pl DECIMAL(15, 2),
            unrealized_plpc DECIMAL(8, 4),
            side VARCHAR(10) DEFAULT 'long',
            purchase_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # NOTE: Data loading tables (stock_symbols, etf_symbols, market_data, etc.)
        # are managed by their respective loader scripts:
        # - loadstocksymbols.py manages stock_symbols and etf_symbols
        # - loadinfo.py manages company_profile and key_metrics  
        # - Other loaders manage their own tables
        # This script only creates webapp-specific tables
    ]
    
    indexes = [
        # Webapp-specific indexes only
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_api_key ON portfolio_metadata(user_id, api_key_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_api_key ON portfolio_holdings(user_id, api_key_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)"
        # NOTE: Data loading table indexes are managed by their respective loader scripts
    ]
    
    try:
        # Create tables
        for i, table_sql in enumerate(tables):
            try:
                cursor.execute(table_sql)
                logger.info(f"Created table {i+1}/{len(tables)}")
            except Exception as e:
                logger.error(f"Failed to create table {i+1}: {e}")
                logger.error(f"Table SQL: {table_sql}")
                raise
        
        # Add missing columns to existing tables if needed
        logger.info("Checking and adding missing columns to portfolio tables")
        
        # Add api_key_id column to portfolio_metadata if it doesn't exist
        try:
            cursor.execute("""
                ALTER TABLE portfolio_metadata 
                ADD COLUMN IF NOT EXISTS api_key_id INTEGER
            """)
            logger.info("Added api_key_id column to portfolio_metadata (if missing)")
            
            # Add unique constraint if it doesn't exist
            try:
                cursor.execute("""
                    ALTER TABLE portfolio_metadata 
                    ADD CONSTRAINT unique_user_api_key UNIQUE (user_id, api_key_id)
                """)
                logger.info("Added unique constraint for user_id, api_key_id")
            except Exception as e:
                logger.info(f"Unique constraint may already exist: {e}")
                
        except Exception as e:
            logger.warning(f"Could not add api_key_id to portfolio_metadata: {e}")
        
        # Add missing columns to portfolio_holdings if they don't exist
        missing_columns = [
            ("api_key_id", "INTEGER"),
            ("current_price", "DECIMAL(10, 4)"),
            ("market_value", "DECIMAL(15, 2)"),
            ("unrealized_pl", "DECIMAL(15, 2)"),
            ("unrealized_plpc", "DECIMAL(8, 4)"),
            ("side", "VARCHAR(10) DEFAULT 'long'")
        ]
        
        for col_name, col_type in missing_columns:
            try:
                cursor.execute(f"""
                    ALTER TABLE portfolio_holdings 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_type}
                """)
                logger.info(f"Added {col_name} column to portfolio_holdings (if missing)")
            except Exception as e:
                logger.warning(f"Could not add {col_name} to portfolio_holdings: {e}")
        
        # Verify portfolio_holdings table structure before creating indexes
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'portfolio_holdings'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        logger.info(f"portfolio_holdings table columns: {columns}")
        
        # Create indexes
        for i, index_sql in enumerate(indexes):
            try:
                cursor.execute(index_sql)
                logger.info(f"Created index {i+1}/{len(indexes)}")
            except Exception as e:
                logger.error(f"Failed to create index {i+1}: {e}")
                logger.error(f"Index SQL: {index_sql}")
                # If it's the portfolio_id index, show table structure
                if "portfolio_id" in index_sql:
                    cursor.execute("SELECT * FROM information_schema.columns WHERE table_name = 'portfolio_holdings'")
                    cols = cursor.fetchall()
                    logger.error(f"Available columns in portfolio_holdings: {cols}")
                raise
        
        # Add foreign key constraints after all tables are created
        # Skip foreign keys for now due to data type incompatibilities in existing tables
        logger.info("Skipping foreign key constraints due to existing table schema incompatibilities")
        
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
        
        # Create triggers for updated_at columns (only for webapp tables)
        triggers = [
            "CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_user_api_keys_updated_at BEFORE UPDATE ON user_api_keys FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_metadata_updated_at BEFORE UPDATE ON portfolio_metadata FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()",
            "CREATE TRIGGER update_portfolio_holdings_updated_at BEFORE UPDATE ON portfolio_holdings FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
        ]
        
        for i, trigger_sql in enumerate(triggers):
            try:
                cursor.execute(f"DROP TRIGGER IF EXISTS {trigger_sql.split()[2]} ON {trigger_sql.split()[6]}")
                cursor.execute(trigger_sql)
                logger.info(f"Created trigger {i+1}/{len(triggers)}")
            except Exception as e:
                logger.warning(f"Trigger {i+1} creation failed: {e}")
        
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