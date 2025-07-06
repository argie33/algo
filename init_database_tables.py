#!/usr/bin/env python3
"""Initialize database tables during deployment."""

import os
import sys
import json
import subprocess
from datetime import datetime

# Ensure packages are available
try:
    import psycopg2
except ImportError:
    print("psycopg2 not found, installing...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "psycopg2-binary"], 
                      check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install psycopg2-binary: {e}")
        sys.exit(1)
    import psycopg2

try:
    import boto3
except ImportError:
    print("boto3 not found, installing...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "boto3"], 
                      check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install boto3: {e}")
        sys.exit(1)
    import boto3


def get_db_credentials(secret_arn):
    """Fetch database credentials from AWS Secrets Manager."""
    print(f"Fetching database credentials from secret: {secret_arn}")
    
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


def create_database_tables(conn):
    """Create database tables."""
    cursor = conn.cursor()
    
    try:
        # Create user_api_keys table
        print("Creating user_api_keys table...")
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
        
        # Create indexes for user_api_keys
        print("Creating indexes for user_api_keys table...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active)")
        
        # Create portfolio_holdings table
        print("Creating portfolio_holdings table...")
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
        
        # Create portfolio_metadata table
        print("Creating portfolio_metadata table...")
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
        
        # Create indexes for portfolio tables
        print("Creating indexes for portfolio tables...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_broker ON portfolio_holdings(broker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_metadata_user_id ON portfolio_metadata(user_id)")
        
        # Commit all changes
        conn.commit()
        print("All database tables created successfully!")
        
        # Verify tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('user_api_keys', 'portfolio_holdings', 'portfolio_metadata')
            ORDER BY table_name
        """)
        
        tables = cursor.fetchall()
        print(f"\nVerified tables exist: {[table[0] for table in tables]}")
        
        # Update last_updated table to track initialization
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                table_name VARCHAR(255) PRIMARY KEY,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            INSERT INTO last_updated (table_name, updated_at) 
            VALUES ('database_tables_init', %s)
            ON CONFLICT (table_name) 
            DO UPDATE SET updated_at = EXCLUDED.updated_at
        """, (datetime.now(),))
        
        conn.commit()
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


def main():
    """Main function to initialize database tables."""
    # Get database secret ARN from environment
    secret_arn = os.environ.get('DB_SECRET_ARN')
    if not secret_arn:
        print("ERROR: DB_SECRET_ARN environment variable not set")
        sys.exit(1)
    
    try:
        # Get database credentials
        db_config = get_db_credentials(secret_arn)
        
        # Connect to database
        print(f"Connecting to database at {db_config['host']}:{db_config['port']}")
        conn = psycopg2.connect(**db_config)
        
        # Create database tables
        create_database_tables(conn)
        
        # Close connection
        conn.close()
        print("\nDatabase tables initialization completed successfully!")
        
    except Exception as e:
        print(f"Failed to initialize database tables: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()