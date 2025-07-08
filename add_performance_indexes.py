#!/usr/bin/env python3
"""
Performance Indexes Script
Adds database indexes to improve health check and markets API performance.
Run this after your main database initialization and data loaders.
"""

import os
import sys
import json
import logging
import psycopg2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration from environment or AWS Secrets Manager"""
    try:
        import boto3
        
        # Try AWS Secrets Manager first
        if os.environ.get('DB_SECRET_ARN'):
            secret_arn = os.environ['DB_SECRET_ARN']
            region = os.environ.get('AWS_REGION', 'us-east-1')
            
            client = boto3.client('secretsmanager', region_name=region)
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response['SecretString'])
            
            return {
                'host': secret['host'],
                'port': secret.get('port', 5432),
                'database': secret['dbname'],
                'user': secret['username'],
                'password': secret['password']
            }
    except Exception as e:
        logger.warning(f"Failed to get AWS secrets: {e}")
    
    # Fallback to environment variables
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': int(os.environ.get('DB_PORT', 5432)),
        'database': os.environ.get('DB_NAME', 'postgres'),
        'user': os.environ.get('DB_USER', 'postgres'),
        'password': os.environ.get('DB_PASSWORD', '')
    }

def create_performance_indexes(conn):
    """Create performance indexes for health check and markets API"""
    cursor = conn.cursor()
    
    try:
        logger.info("Creating performance indexes...")
        
        # Indexes for market_data table (markets API performance)
        indexes = [
            # Market data indexes (created by loadinfo.py)
            {
                'name': 'idx_market_data_ticker',
                'table': 'market_data',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_market_data_ticker ON market_data(ticker);'
            },
            {
                'name': 'idx_market_data_market_cap',
                'table': 'market_data', 
                'sql': 'CREATE INDEX IF NOT EXISTS idx_market_data_market_cap ON market_data(market_cap) WHERE market_cap IS NOT NULL;'
            },
            
            # Price data indexes (created by loadpricedaily.py)
            {
                'name': 'idx_price_daily_date',
                'table': 'price_daily',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date);'
            },
            {
                'name': 'idx_price_daily_symbol_date',
                'table': 'price_daily',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_price_daily_symbol_date ON price_daily(symbol, date);'
            },
            {
                'name': 'idx_price_daily_date_change',
                'table': 'price_daily',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_price_daily_date_change ON price_daily(date, change_percent) WHERE change_percent IS NOT NULL;'
            },
            
            # Symbol table indexes (created by init_database_combined.sql)
            {
                'name': 'idx_stock_symbols_symbol',
                'table': 'stock_symbols',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols(symbol);'
            },
            
            # Health status indexes (created by health check)
            {
                'name': 'idx_health_status_table_name',
                'table': 'health_status',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_health_status_table_name ON health_status(table_name);'
            },
            {
                'name': 'idx_health_status_last_checked',
                'table': 'health_status',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_health_status_last_checked ON health_status(last_checked);'
            },
            {
                'name': 'idx_health_status_critical',
                'table': 'health_status',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_health_status_critical ON health_status(critical_table, status);'
            },
            
            # Portfolio indexes (created by init_database_combined.py)
            {
                'name': 'idx_portfolio_holdings_user_id',
                'table': 'portfolio_holdings',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_user_id ON portfolio_holdings(user_id);'
            },
            {
                'name': 'idx_portfolio_holdings_symbol',
                'table': 'portfolio_holdings',
                'sql': 'CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_symbol ON portfolio_holdings(symbol);'
            }
        ]
        
        # Create each index with error handling
        created_count = 0
        skipped_count = 0
        
        for index_info in indexes:
            try:
                # Check if table exists first
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """, (index_info['table'],))
                
                table_exists = cursor.fetchone()[0]
                
                if not table_exists:
                    logger.warning(f"Table {index_info['table']} does not exist, skipping index {index_info['name']}")
                    skipped_count += 1
                    continue
                
                # Create the index
                cursor.execute(index_info['sql'])
                logger.info(f"✓ Created index: {index_info['name']} on {index_info['table']}")
                created_count += 1
                
            except psycopg2.Error as e:
                if "already exists" in str(e):
                    logger.info(f"✓ Index {index_info['name']} already exists")
                    created_count += 1
                else:
                    logger.error(f"✗ Failed to create index {index_info['name']}: {e}")
                    skipped_count += 1
        
        # Commit all changes
        conn.commit()
        
        logger.info(f"Index creation complete: {created_count} created/verified, {skipped_count} skipped")
        
        # Analyze tables for better query planning
        logger.info("Running ANALYZE to update table statistics...")
        tables_to_analyze = ['market_data', 'price_daily', 'stock_symbols', 'health_status', 'portfolio_holdings']
        
        for table in tables_to_analyze:
            try:
                cursor.execute(f"ANALYZE {table};")
                logger.info(f"✓ Analyzed table: {table}")
            except psycopg2.Error as e:
                logger.warning(f"Could not analyze table {table}: {e}")
        
        conn.commit()
        logger.info("Performance optimization complete!")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()

def main():
    """Main execution function"""
    logger.info("Starting performance index creation...")
    
    try:
        # Get database configuration
        db_config = get_db_config()
        logger.info(f"Connecting to database: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
        # Connect to database
        conn = psycopg2.connect(**db_config)
        logger.info("Database connection established")
        
        # Create performance indexes
        create_performance_indexes(conn)
        
        logger.info("Performance optimization completed successfully!")
        
    except Exception as e:
        logger.error(f"Performance optimization failed: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info("Database connection closed")

if __name__ == "__main__":
    main()