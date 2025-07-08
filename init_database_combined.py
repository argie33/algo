#!/usr/bin/env python3
"""
Combined Database Initialization Script
Combines all database initialization functionality into a single comprehensive script.
Handles AWS Secrets Manager, package installation, and comprehensive table creation.
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure packages are available
def install_required_packages():
    """Install required packages if not available"""
    required_packages = [
        ('psycopg2', 'psycopg2-binary'),
        ('boto3', 'boto3')
    ]
    
    for package, install_name in required_packages:
        try:
            __import__(package)
            logger.info(f"{package} already installed")
        except ImportError:
            logger.info(f"{package} not found, installing {install_name}...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--user", install_name], 
                              check=True, capture_output=True, text=True)
                logger.info(f"Successfully installed {install_name}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install {install_name}: {e}")
                sys.exit(1)

# Install packages first
install_required_packages()

# Now import the packages after refreshing the module path
import importlib
import site

# Refresh the module search paths to include newly installed packages
importlib.invalidate_caches()
site.main()

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    logger.error(f"Failed to import psycopg2 after installation: {e}")
    sys.exit(1)

try:
    import boto3
except ImportError as e:
    logger.error(f"Failed to import boto3 after installation: {e}")
    sys.exit(1)

def get_db_credentials(secret_arn):
    """Fetch database credentials from AWS Secrets Manager."""
    logger.info(f"Fetching database credentials from secret: {secret_arn}")
    
    try:
        client = boto3.client('secretsmanager', region_name='us-east-1')
        response = client.get_secret_value(SecretId=secret_arn)
        secret = json.loads(response['SecretString'])
        
        return {
            'host': secret['host'],
            'port': secret.get('port', 5432),
            'database': secret.get('dbname', 'postgres'),
            'user': secret['username'],
            'password': secret['password']
        }
    except Exception as e:
        logger.error(f"Failed to get database credentials: {e}")
        return None

def execute_sql_file(cursor, conn, sql_file_path):
    """Execute SQL commands from a file"""
    logger.info(f"Executing SQL file: {sql_file_path}")
    
    try:
        with open(sql_file_path, 'r') as file:
            sql_content = file.read()
        
        # Execute the SQL content
        cursor.execute(sql_content)
        conn.commit()
        logger.info(f"Successfully executed {sql_file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error executing SQL file {sql_file_path}: {e}")
        conn.rollback()
        return False

def create_all_tables(conn):
    """Create all database tables using the combined SQL script."""
    cursor = conn.cursor()
    
    try:
        # Path to the combined SQL file
        sql_file_path = os.path.join(os.path.dirname(__file__), 'init_database_combined.sql')
        
        if os.path.exists(sql_file_path):
            logger.info("Using combined SQL file for table creation")
            success = execute_sql_file(cursor, conn, sql_file_path)
            if not success:
                raise Exception("Failed to execute combined SQL file")
        else:
            logger.info("Combined SQL file not found, creating tables manually")
            create_tables_manually(cursor, conn)
        
        # Verify critical tables exist
        verify_tables(cursor)
        
        logger.info("All database tables created successfully!")
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()

def create_tables_manually(cursor, conn):
    """Create tables manually if SQL file is not available"""
    logger.info("Creating tables manually...")
    
    # Create core tables
    logger.info("Creating core tables...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            market VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run TIMESTAMP WITH TIME ZONE
        )
    """)
    
    # Create API keys table
    logger.info("Creating user_api_keys table...")
    cursor.execute("""
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
    """)
    
    # Create portfolio tables
    logger.info("Creating portfolio tables...")
    cursor.execute("""
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
        )
    """)
    
    cursor.execute("""
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
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trading_alerts (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            symbol VARCHAR(10) NOT NULL,
            alert_type VARCHAR(50) NOT NULL,
            target_value DECIMAL(12,4),
            current_value DECIMAL(12,4),
            condition_met BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            message TEXT,
            triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create watchlist tables
    logger.info("Creating watchlist tables...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            color VARCHAR(7) DEFAULT '#1976d2',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id SERIAL PRIMARY KEY,
            watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
            symbol VARCHAR(10) NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            alert_price DECIMAL(12,4),
            alert_type VARCHAR(20) CHECK (alert_type IN ('above', 'below', 'change_percent')),
            alert_value DECIMAL(12,4),
            position_order INTEGER DEFAULT 0,
            UNIQUE(watchlist_id, symbol)
        )
    """)
    
    # Create health_status table
    logger.info("Creating health_status table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_status (
            table_name VARCHAR(255) PRIMARY KEY,
            status VARCHAR(50) NOT NULL DEFAULT 'unknown',
            record_count BIGINT DEFAULT 0,
            missing_data_count BIGINT DEFAULT 0,
            last_updated TIMESTAMP WITH TIME ZONE,
            last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_stale BOOLEAN DEFAULT FALSE,
            error TEXT,
            table_category VARCHAR(100),
            critical_table BOOLEAN DEFAULT FALSE,
            expected_update_frequency INTERVAL DEFAULT '1 day',
            size_bytes BIGINT DEFAULT 0,
            last_vacuum TIMESTAMP WITH TIME ZONE,
            last_analyze TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create trigger function for health_status
    cursor.execute("""
        CREATE OR REPLACE FUNCTION update_health_status_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trigger_health_status_updated_at
            BEFORE UPDATE ON health_status
            FOR EACH ROW
            EXECUTE FUNCTION update_health_status_updated_at();
    """)
    
    # Initialize health_status table with core tables
    logger.info("Initializing health_status table data...")
    cursor.execute("""
        INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency) VALUES
        ('user_api_keys', 'system', true, '1 hour'),
        ('portfolio_holdings', 'trading', true, '1 hour'),
        ('portfolio_metadata', 'trading', true, '1 hour'),
        ('trading_alerts', 'trading', false, '1 hour'),
        ('watchlists', 'trading', false, '1 hour'),
        ('watchlist_items', 'trading', false, '1 hour'),
        ('stocks', 'symbols', true, '1 week'),
        ('last_updated', 'system', true, '1 hour'),
        ('health_status', 'system', true, '1 hour')
        ON CONFLICT (table_name) DO NOTHING
    """)
    
    # Create indexes
    logger.info("Creating indexes...")
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider)",
        "CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker)",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_trading_alerts_user_id ON trading_alerts(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_trading_alerts_symbol ON trading_alerts(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_trading_alerts_active ON trading_alerts(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id)",
        "CREATE INDEX IF NOT EXISTS idx_watchlist_items_symbol ON watchlist_items(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_status ON health_status(status)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_last_updated ON health_status(last_updated)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_category ON health_status(table_category)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table)",
        "CREATE INDEX IF NOT EXISTS idx_health_status_stale ON health_status(is_stale)"
    ]
    
    for index_sql in indexes:
        cursor.execute(index_sql)
    
    conn.commit()

def verify_tables(cursor):
    """Verify that critical tables exist"""
    logger.info("Verifying table creation...")
    
    critical_tables = [
        'user_api_keys',
        'portfolio_holdings', 
        'portfolio_metadata',
        'last_updated',
        'watchlists',
        'watchlist_items',
        'health_status'
    ]
    
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = ANY(%s)
        ORDER BY table_name
    """, (critical_tables,))
    
    existing_tables = [row[0] for row in cursor.fetchall()]
    missing_tables = set(critical_tables) - set(existing_tables)
    
    if missing_tables:
        logger.warning(f"Missing critical tables: {missing_tables}")
    else:
        logger.info("All critical tables verified successfully")
    
    logger.info(f"Existing tables: {existing_tables}")

def update_health_status(conn):
    """Update health status for all tables after creation"""
    cursor = conn.cursor()
    
    try:
        # Create function to update health status for a specific table
        cursor.execute("""
            CREATE OR REPLACE FUNCTION update_table_health_status(
                p_table_name VARCHAR(255),
                p_status VARCHAR(50) DEFAULT NULL,
                p_record_count BIGINT DEFAULT NULL,
                p_missing_data_count BIGINT DEFAULT NULL,
                p_last_updated TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                p_error TEXT DEFAULT NULL
            )
            RETURNS VOID AS $$
            BEGIN
                INSERT INTO health_status (
                    table_name, 
                    status, 
                    record_count, 
                    missing_data_count, 
                    last_updated, 
                    last_checked, 
                    is_stale, 
                    error
                ) VALUES (
                    p_table_name,
                    COALESCE(p_status, 'unknown'),
                    COALESCE(p_record_count, 0),
                    COALESCE(p_missing_data_count, 0),
                    p_last_updated,
                    CURRENT_TIMESTAMP,
                    CASE 
                        WHEN p_last_updated IS NULL THEN false
                        WHEN p_last_updated < (CURRENT_TIMESTAMP - INTERVAL '7 days') THEN true
                        ELSE false
                    END,
                    p_error
                )
                ON CONFLICT (table_name) 
                DO UPDATE SET
                    status = COALESCE(EXCLUDED.status, health_status.status),
                    record_count = COALESCE(EXCLUDED.record_count, health_status.record_count),
                    missing_data_count = COALESCE(EXCLUDED.missing_data_count, health_status.missing_data_count),
                    last_updated = COALESCE(EXCLUDED.last_updated, health_status.last_updated),
                    last_checked = EXCLUDED.last_checked,
                    is_stale = EXCLUDED.is_stale,
                    error = EXCLUDED.error,
                    updated_at = CURRENT_TIMESTAMP;
            END;
            $$ LANGUAGE plpgsql;
        """)
        
        # Update health status for all tables that exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        
        existing_tables = [row[0] for row in cursor.fetchall()]
        
        for table_name in existing_tables:
            try:
                # Get record count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                record_count = cursor.fetchone()[0]
                
                # Update health status
                cursor.execute("""
                    SELECT update_table_health_status(%s, %s, %s, %s, %s, %s)
                """, (table_name, 'healthy' if record_count >= 0 else 'empty', record_count, 0, datetime.now(), None))
                
            except Exception as e:
                logger.warning(f"Error updating health status for {table_name}: {e}")
                # Mark as error
                cursor.execute("""
                    SELECT update_table_health_status(%s, %s, %s, %s, %s, %s)
                """, (table_name, 'error', 0, 0, None, str(e)))
        
        conn.commit()
        logger.info("Updated health status for all tables")
        
    except Exception as e:
        logger.error(f"Error updating health status: {e}")
        conn.rollback()
    finally:
        cursor.close()

def update_last_run_tracking(conn):
    """Update the last_updated table to track script execution"""
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO last_updated (script_name, last_run) 
            VALUES ('init_database_combined.py', %s)
            ON CONFLICT (script_name) 
            DO UPDATE SET last_run = EXCLUDED.last_run
        """, (datetime.now(),))
        
        conn.commit()
        logger.info("Updated last_updated tracking")
        
    except Exception as e:
        logger.error(f"Error updating last_updated tracking: {e}")
        conn.rollback()
    finally:
        cursor.close()

def main():
    """Main function to initialize all database tables."""
    logger.info("Starting combined database initialization...")
    
    # Get database secret ARN from environment
    secret_arn = os.environ.get('DB_SECRET_ARN')
    if not secret_arn:
        logger.error("ERROR: DB_SECRET_ARN environment variable not set")
        sys.exit(1)
    
    try:
        # Get database credentials
        db_config = get_db_credentials(secret_arn)
        if not db_config:
            logger.error("Failed to get database configuration")
            sys.exit(1)
        
        # Connect to database
        logger.info(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        conn = psycopg2.connect(**db_config)
        conn.autocommit = False
        
        # Create all database tables
        create_all_tables(conn)
        
        # Update health status for all tables
        update_health_status(conn)
        
        # Update tracking
        update_last_run_tracking(conn)
        
        # Close connection
        conn.close()
        logger.info("Combined database initialization completed successfully!")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()