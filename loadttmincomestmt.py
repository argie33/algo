#!/usr/bin/env python3
"""
Load TTM Income Statement data from Yahoo Finance API and store in database.
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

def create_ttm_income_stmt_table():
    """Create the TTM income statement table if it doesn't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create the table if it doesn't exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ttm_income_stmt (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            gross_profit NUMERIC,
            revenue NUMERIC,
            cost_of_revenue NUMERIC,
            operating_income NUMERIC,
            operating_expense NUMERIC,
            selling_general_administrative NUMERIC,
            research_development NUMERIC,
            net_income NUMERIC,
            interest_expense NUMERIC,
            income_tax_expense NUMERIC,
            income_before_tax NUMERIC,
            other_items NUMERIC,
            ebit NUMERIC,
            net_income_from_continuing_operations NUMERIC,
            normalized_income NUMERIC,
            net_income_applicable_to_common_shares NUMERIC,
            tax_provision NUMERIC,
            tax_effect_of_unusual_items NUMERIC,
            basic_eps NUMERIC,
            diluted_eps NUMERIC,
            weighted_average_shares NUMERIC,
            weighted_average_shares_diluted NUMERIC,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """)
        
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error creating TTM income statement table: {e}")
        raise
    finally:
        if conn:
            conn.close()

def load_ttm_income_stmt_for_symbol(symbol):
    """Load TTM income statement data for a given symbol."""
    conn = None
    try:
        # Get the ticker data
        ticker = yf.Ticker(symbol)
        ttm_income_stmt = ticker.ttm_income_stmt
        
        if ttm_income_stmt is None or ttm_income_stmt.empty:
            logger.info(f"No TTM income statement data available for {symbol}")
            return 0
        
        # Convert to records
        records = []
        
        # Get the date (column name)
        if len(ttm_income_stmt.columns) > 0:
            date_col = ttm_income_stmt.columns[0]  # First column is the date
            
            # Extract data
            record = {
                'symbol': symbol,
                'date': date_col,
                'gross_profit': ttm_income_stmt.loc['Gross Profit', date_col] if 'Gross Profit' in ttm_income_stmt.index else None,
                'revenue': ttm_income_stmt.loc['Total Revenue', date_col] if 'Total Revenue' in ttm_income_stmt.index else None,
                'cost_of_revenue': ttm_income_stmt.loc['Cost Of Revenue', date_col] if 'Cost Of Revenue' in ttm_income_stmt.index else None,
                'operating_income': ttm_income_stmt.loc['Operating Income', date_col] if 'Operating Income' in ttm_income_stmt.index else None,
                'operating_expense': ttm_income_stmt.loc['Operating Expense', date_col] if 'Operating Expense' in ttm_income_stmt.index else None,
                'selling_general_administrative': ttm_income_stmt.loc['Selling General Administrative', date_col] if 'Selling General Administrative' in ttm_income_stmt.index else None,
                'research_development': ttm_income_stmt.loc['Research Development', date_col] if 'Research Development' in ttm_income_stmt.index else None,
                'net_income': ttm_income_stmt.loc['Net Income', date_col] if 'Net Income' in ttm_income_stmt.index else None,
                'interest_expense': ttm_income_stmt.loc['Interest Expense', date_col] if 'Interest Expense' in ttm_income_stmt.index else None,
                'income_tax_expense': ttm_income_stmt.loc['Income Tax Expense', date_col] if 'Income Tax Expense' in ttm_income_stmt.index else None,
                'income_before_tax': ttm_income_stmt.loc['Income Before Tax', date_col] if 'Income Before Tax' in ttm_income_stmt.index else None,
                'other_items': ttm_income_stmt.loc['Other Items', date_col] if 'Other Items' in ttm_income_stmt.index else None,
                'ebit': ttm_income_stmt.loc['EBIT', date_col] if 'EBIT' in ttm_income_stmt.index else None,
                'net_income_from_continuing_operations': ttm_income_stmt.loc['Net Income From Continuing Operations', date_col] if 'Net Income From Continuing Operations' in ttm_income_stmt.index else None,
                'normalized_income': ttm_income_stmt.loc['Normalized Income', date_col] if 'Normalized Income' in ttm_income_stmt.index else None,
                'net_income_applicable_to_common_shares': ttm_income_stmt.loc['Net Income Applicable To Common Shares', date_col] if 'Net Income Applicable To Common Shares' in ttm_income_stmt.index else None,
                'tax_provision': ttm_income_stmt.loc['Tax Provision', date_col] if 'Tax Provision' in ttm_income_stmt.index else None,
                'tax_effect_of_unusual_items': ttm_income_stmt.loc['Tax Effect Of Unusual Items', date_col] if 'Tax Effect Of Unusual Items' in ttm_income_stmt.index else None,
                'basic_eps': ttm_income_stmt.loc['Basic EPS', date_col] if 'Basic EPS' in ttm_income_stmt.index else None,
                'diluted_eps': ttm_income_stmt.loc['Diluted EPS', date_col] if 'Diluted EPS' in ttm_income_stmt.index else None,
                'weighted_average_shares': ttm_income_stmt.loc['Weighted Average Shares', date_col] if 'Weighted Average Shares' in ttm_income_stmt.index else None,
                'weighted_average_shares_diluted': ttm_income_stmt.loc['Weighted Average Shares Diluted', date_col] if 'Weighted Average Shares Diluted' in ttm_income_stmt.index else None
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
            INSERT INTO ttm_income_stmt ({column_names})
            VALUES ({values_template})
            ON CONFLICT (symbol, date) DO UPDATE SET
            """
            
            # Exclude primary key fields from the update
            update_columns = [col for col in columns if col not in ['symbol', 'date']]
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
        logger.error(f"Error loading TTM income statement data for {symbol}: {e}")
        return 0
    finally:
        if conn:
            conn.close()
        # Clean up memory
        gc.collect()

def main():
    """Main function to load TTM income statement data for all stocks."""
    try:
        # Create table if it doesn't exist
        create_ttm_income_stmt_table()
        
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
                    records_loaded = load_ttm_income_stmt_for_symbol(symbol)
                    if records_loaded > 0:
                        successful_loads += 1
                        logger.info(f"Successfully loaded {records_loaded} TTM income statement records for {symbol}")
                    break
                except Exception as e:
                    retries += 1
                    logger.warning(f"Attempt {retries}/{max_retries} failed for {symbol}: {e}")
                    if retries < max_retries:
                        time.sleep(2)  # Wait before retrying
                    else:
                        logger.error(f"Failed to load TTM income statement data for {symbol} after {max_retries} attempts")
            
            # Sleep to avoid rate limiting
            if i % 5 == 0 and i > 0:
                logger.info(f"Processed {i} symbols. Taking a short break...")
                time.sleep(1)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        logger.info(f"TTM income statement data loading completed. Successfully loaded data for {successful_loads}/{len(symbols)} symbols in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
