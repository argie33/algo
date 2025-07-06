#!/usr/bin/env python3
"""
Lambda function for database initialization.
This runs as a CloudFormation custom resource during stack deployment.
"""
import json
import boto3
import psycopg2
import cfnresponse
import logging
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_db_credentials(secret_arn):
    """Fetch database credentials from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_arn)
    return json.loads(response['SecretString'])

def create_tables(conn):
    """Create all required database tables."""
    cursor = conn.cursor()
    
    # Base tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS symbols (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(255),
            sector VARCHAR(100),
            industry VARCHAR(100),
            market_cap BIGINT,
            ipo_year INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS price_daily (
            symbol VARCHAR(10),
            date DATE,
            open DECIMAL(10, 2),
            high DECIMAL(10, 2),
            low DECIMAL(10, 2),
            close DECIMAL(10, 2),
            volume BIGINT,
            PRIMARY KEY (symbol, date),
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS technical_indicators (
            symbol VARCHAR(10),
            date DATE,
            rsi DECIMAL(5, 2),
            macd DECIMAL(10, 4),
            macd_signal DECIMAL(10, 4),
            macd_hist DECIMAL(10, 4),
            bb_upper DECIMAL(10, 2),
            bb_middle DECIMAL(10, 2),
            bb_lower DECIMAL(10, 2),
            PRIMARY KEY (symbol, date),
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sentiment_data (
            symbol VARCHAR(10),
            date DATE,
            sentiment_score DECIMAL(5, 2),
            news_count INTEGER,
            social_mentions INTEGER,
            PRIMARY KEY (symbol, date),
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS earnings_data (
            symbol VARCHAR(10),
            fiscal_date_ending DATE,
            reported_eps DECIMAL(10, 4),
            estimated_eps DECIMAL(10, 4),
            surprise DECIMAL(10, 4),
            surprise_percentage DECIMAL(5, 2),
            PRIMARY KEY (symbol, fiscal_date_ending),
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS market_data (
            date DATE PRIMARY KEY,
            vix DECIMAL(10, 2),
            sp500 DECIMAL(10, 2),
            nasdaq DECIMAL(10, 2),
            dow DECIMAL(10, 2),
            treasury_10y DECIMAL(5, 2),
            dxy DECIMAL(10, 2)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS economic_data (
            date DATE,
            indicator VARCHAR(50),
            value DECIMAL(20, 4),
            PRIMARY KEY (date, indicator)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS portfolio_holdings (
            portfolio_id VARCHAR(50),
            symbol VARCHAR(10),
            quantity DECIMAL(20, 8),
            avg_cost DECIMAL(10, 2),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (portfolio_id, symbol),
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trade_signals (
            signal_id SERIAL PRIMARY KEY,
            symbol VARCHAR(10),
            signal_date TIMESTAMP,
            signal_type VARCHAR(10),
            price DECIMAL(10, 2),
            confidence DECIMAL(5, 2),
            executed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (symbol) REFERENCES symbols(symbol)
        )
        """
    ]
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_price_daily_date ON price_daily(date)",
        "CREATE INDEX IF NOT EXISTS idx_technical_indicators_date ON technical_indicators(date)",
        "CREATE INDEX IF NOT EXISTS idx_sentiment_data_date ON sentiment_data(date)",
        "CREATE INDEX IF NOT EXISTS idx_trade_signals_date ON trade_signals(signal_date)",
        "CREATE INDEX IF NOT EXISTS idx_trade_signals_executed ON trade_signals(executed)"
    ]
    
    try:
        # Create tables
        for table_sql in tables:
            cursor.execute(table_sql)
            logger.info(f"Table created successfully")
        
        # Create indexes
        for index_sql in indexes:
            cursor.execute(index_sql)
            logger.info(f"Index created successfully")
        
        conn.commit()
        logger.info("All tables and indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating tables: {str(e)}")
        conn.rollback()
        raise
    finally:
        cursor.close()

def handler(event, context):
    """Lambda handler for CloudFormation custom resource."""
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        request_type = event['RequestType']
        
        if request_type == 'Delete':
            # Nothing to do on delete
            cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
            return
        
        # Get the secret ARN from the event
        secret_arn = event['ResourceProperties']['SecretArn']
        
        # Get database credentials
        db_creds = get_db_credentials(secret_arn)
        
        # Connect to database
        conn = psycopg2.connect(
            host=db_creds['host'],
            port=db_creds['port'],
            database=db_creds['dbname'],
            user=db_creds['username'],
            password=db_creds['password']
        )
        
        # Create tables
        create_tables(conn)
        
        # Close connection
        conn.close()
        
        # Send success response
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {
            'Message': 'Database initialized successfully'
        })
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        cfnresponse.send(event, context, cfnresponse.FAILED, {
            'Error': str(e)
        })