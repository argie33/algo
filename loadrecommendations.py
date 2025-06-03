#!/usr/bin/env python3   
"""
Load analyst recommendations data from Yahoo Finance API and store in database.
"""
import os
import logging
import time
import boto3
import psycopg2
from psycopg2 import sql
import pandas as pd
import yfinance as yf
from datetime import datetime
import numpy as np
import sys
import gc

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Function to get DB connection
def get_db_connection():
    """Create a connection to the PostgreSQL database."""
    try:
        # Check if we're running in AWS (using AWS Secrets Manager)
        db_secret_arn = os.environ.get('DB_SECRET_ARN')
        if db_secret_arn:
            logger.info("Using AWS Secrets Manager for database credentials")
            session = boto3.session.Session()
            client = session.client(service_name='secretsmanager')
            secret_value = client.get_secret_value(SecretId=db_secret_arn)
            secret = eval(secret_value['SecretString'])
            
            # Extract credentials from the secret
            db_host = os.environ.get('DB_HOST')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME')
            db_user = os.environ.get('DB_USER')
            db_password = secret['password']
        else:
            # Local development using environment variables
            logger.info("Using environment variables for database credentials")
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_port = os.environ.get('DB_PORT', '5432')
            db_name = os.environ.get('DB_NAME', 'stocks')
            db_user = os.environ.get('DB_USER', 'postgres')
            db_password = os.environ.get('DB_PASSWORD', 'postgres')
        
        # Establish the connection
        connection = psycopg2.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password
        )
        return connection
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        raise

def get_stock_symbols():
    """Get the list of stock symbols from the database."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get active symbols
        cur.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]
        
        cur.close()
        return symbols
    except Exception as e:
        logger.error(f"Error getting stock symbols: {e}")
        raise
    finally:
        if conn:
            conn.close()

def create_recommendations_table():
    """Create the analyst recommendations table if it doesn't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create the table if it doesn't exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS analyst_recommendations (
            symbol VARCHAR(10) NOT NULL,
            period VARCHAR(10) NOT NULL,
            strong_buy INTEGER,
            buy INTEGER,
            hold INTEGER,
            sell INTEGER,
            strong_sell INTEGER,
            collected_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, period, collected_date)
        );
        """)
        
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error creating recommendations table: {e}")
        raise
    finally:
        if conn:
            conn.close()

def load_recommendations_for_symbol(symbol):
    """Load analyst recommendations data for a given symbol."""
    conn = None
    try:
        # Get the ticker data
        ticker = yf.Ticker(symbol)
        recommendations = ticker.recommendations
        
        if recommendations is None or recommendations.empty:
            logger.info(f"No recommendations data available for {symbol}")
            return 0
        
        # Convert to records
        records = []
        
        # In recommendations, 'period' is the index (e.g., '0m', '-1m', '-2m')
        # and columns are 'strongBuy', 'buy', 'hold', 'sell', 'strongSell'
        for period, row in recommendations.iterrows():
            record = {
                'symbol': symbol,
                'period': period,
                'strong_buy': int(row['strongBuy']) if 'strongBuy' in row and not pd.isna(row['strongBuy']) else 0,
                'buy': int(row['buy']) if 'buy' in row and not pd.isna(row['buy']) else 0,
                'hold': int(row['hold']) if 'hold' in row and not pd.isna(row['hold']) else 0,
                'sell': int(row['sell']) if 'sell' in row and not pd.isna(row['sell']) else 0,
                'strong_sell': int(row['strongSell']) if 'strongSell' in row and not pd.isna(row['strongSell']) else 0
            }
            records.append(record)
        
        # Insert into database
        if records:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Build SQL query dynamically
            columns = list(records[0].keys())
            values_template = ", ".join(["%s"] * len(columns))
            column_names = ", ".join([sql.Identifier(col).as_string(conn) for col in columns])
            
            upsert_stmt = f"""
            INSERT INTO analyst_recommendations ({column_names})
            VALUES ({values_template})
            ON CONFLICT (symbol, period, collected_date) DO UPDATE SET
            """
            
            # Exclude primary key fields from the update
            update_columns = [col for col in columns if col not in ['symbol', 'period']]
            update_stmt = ", ".join([f"{sql.Identifier(col).as_string(conn)} = EXCLUDED.{sql.Identifier(col).as_string(conn)}" for col in update_columns])
            upsert_stmt += update_stmt
            
            # Execute the query for each record
            for record in records:
                values = [record[col] for col in columns]
                cur.execute(upsert_stmt, values)
            
            conn.commit()
            cur.close()
            
            return len(records)
        else:
            return 0
            
    except Exception as e:
        logger.error(f"Error loading recommendations data for {symbol}: {e}")
        return 0
    finally:
        if conn:
            conn.close()
        # Clean up memory
        gc.collect()

def main():
    """Main function to load analyst recommendations data for all stocks."""
    try:
        # Create table if it doesn't exist
        create_recommendations_table()
        
        # Get the list of stock symbols
        symbols = get_stock_symbols()
        logger.info(f"Found {len(symbols)} stock symbols")
        
        # Process each symbol
        successful_loads = 0
        start_time = time.time()
        
        for i, symbol in enumerate(symbols):
            logger.info(f"Processing {symbol} ({i+1}/{len(symbols)})")
            
            # Use retry mechanism
            max_retries = 3
            retries = 0
            
            while retries < max_retries:
                try:
                    records_loaded = load_recommendations_for_symbol(symbol)
                    if records_loaded > 0:
                        successful_loads += 1
                        logger.info(f"Successfully loaded {records_loaded} recommendation records for {symbol}")
                    break
                except Exception as e:
                    retries += 1
                    logger.warning(f"Attempt {retries}/{max_retries} failed for {symbol}: {e}")
                    if retries < max_retries:
                        time.sleep(2)  # Wait before retrying
                    else:
                        logger.error(f"Failed to load recommendations data for {symbol} after {max_retries} attempts")
            
            # Sleep to avoid rate limiting
            if i % 5 == 0 and i > 0:
                logger.info(f"Processed {i} symbols. Taking a short break...")
                time.sleep(1)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        logger.info(f"Analyst recommendations data loading completed. Successfully loaded data for {successful_loads}/{len(symbols)} symbols in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
