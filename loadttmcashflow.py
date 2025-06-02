#!/usr/bin/env python3
"""
Load TTM Cash Flow data from Yahoo Finance API and store in database.
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

def create_ttm_cash_flow_table():
    """Create the TTM cash flow table if it doesn't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create the table if it doesn't exist
        cur.execute("""
        CREATE TABLE IF NOT EXISTS ttm_cash_flow (
            symbol VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            free_cash_flow NUMERIC,
            repurchase_of_capital_stock NUMERIC,
            repayment_of_debt NUMERIC,
            capital_expenditure NUMERIC,
            income_tax_paid NUMERIC,
            end_cash_position NUMERIC,
            beginning_cash_position NUMERIC,
            changes_in_cash NUMERIC,
            financing_cash_flow NUMERIC,
            cash_flow_from_continuing_financing_activities NUMERIC,
            net_other_financing_charges NUMERIC,
            cash_dividends_paid NUMERIC,
            common_stock_dividend_paid NUMERIC,
            net_common_stock_issuance NUMERIC,
            common_stock_payments NUMERIC,
            net_issuance_payments_of_debt NUMERIC,
            net_short_term_debt_issuance NUMERIC,
            net_long_term_debt_issuance NUMERIC,
            long_term_debt_payments NUMERIC,
            investing_cash_flow NUMERIC,
            cash_flow_from_continuing_investing_activities NUMERIC,
            net_other_investing_changes NUMERIC,
            net_investment_purchase_and_sale NUMERIC,
            sale_of_investment NUMERIC,
            purchase_of_investment NUMERIC,
            net_ppe_purchase_and_sale NUMERIC,
            purchase_of_ppe NUMERIC,
            operating_cash_flow NUMERIC,
            cash_flow_from_continuing_operating_activities NUMERIC,
            change_in_working_capital NUMERIC,
            change_in_other_current_liabilities NUMERIC,
            change_in_other_current_assets NUMERIC,
            change_in_payables_and_accrued_expense NUMERIC,
            change_in_payable NUMERIC,
            change_in_account_payable NUMERIC,
            change_in_inventory NUMERIC,
            change_in_receivables NUMERIC,
            changes_in_account_receivables NUMERIC,
            other_non_cash_items NUMERIC,
            stock_based_compensation NUMERIC,
            depreciation_amortization_depletion NUMERIC,
            depreciation_and_amortization NUMERIC,
            net_income_from_continuing_operations NUMERIC,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, date)
        );
        """)
        
        conn.commit()
        cur.close()
    except Exception as e:
        logger.error(f"Error creating TTM cash flow table: {e}")
        raise
    finally:
        if conn:
            conn.close()

def load_ttm_cash_flow_for_symbol(symbol):
    """Load TTM cash flow data for a given symbol."""
    conn = None
    try:
        # Get the ticker data
        ticker = yf.Ticker(symbol)
        ttm_cash_flow = ticker.ttm_cash_flow
        
        if ttm_cash_flow is None or ttm_cash_flow.empty:
            logger.info(f"No TTM cash flow data available for {symbol}")
            return 0
        
        # Convert to records
        records = []
        
        # Get the date (column name)
        if len(ttm_cash_flow.columns) > 0:
            date_col = ttm_cash_flow.columns[0]  # First column is the date
            
            # Extract data
            record = {
                'symbol': symbol,
                'date': date_col,
                'free_cash_flow': ttm_cash_flow.loc['Free Cash Flow', date_col] if 'Free Cash Flow' in ttm_cash_flow.index else None,
                'repurchase_of_capital_stock': ttm_cash_flow.loc['Repurchase Of Capital Stock', date_col] if 'Repurchase Of Capital Stock' in ttm_cash_flow.index else None,
                'repayment_of_debt': ttm_cash_flow.loc['Repayment Of Debt', date_col] if 'Repayment Of Debt' in ttm_cash_flow.index else None,
                'capital_expenditure': ttm_cash_flow.loc['Capital Expenditure', date_col] if 'Capital Expenditure' in ttm_cash_flow.index else None,
                'income_tax_paid': ttm_cash_flow.loc['Income Tax Paid Supplemental Data', date_col] if 'Income Tax Paid Supplemental Data' in ttm_cash_flow.index else None,
                'end_cash_position': ttm_cash_flow.loc['End Cash Position', date_col] if 'End Cash Position' in ttm_cash_flow.index else None,
                'beginning_cash_position': ttm_cash_flow.loc['Beginning Cash Position', date_col] if 'Beginning Cash Position' in ttm_cash_flow.index else None,
                'changes_in_cash': ttm_cash_flow.loc['Changes In Cash', date_col] if 'Changes In Cash' in ttm_cash_flow.index else None,
                'financing_cash_flow': ttm_cash_flow.loc['Financing Cash Flow', date_col] if 'Financing Cash Flow' in ttm_cash_flow.index else None,
                'cash_flow_from_continuing_financing_activities': ttm_cash_flow.loc['Cash Flow From Continuing Financing Activities', date_col] if 'Cash Flow From Continuing Financing Activities' in ttm_cash_flow.index else None,
                'net_other_financing_charges': ttm_cash_flow.loc['Net Other Financing Charges', date_col] if 'Net Other Financing Charges' in ttm_cash_flow.index else None,
                'cash_dividends_paid': ttm_cash_flow.loc['Cash Dividends Paid', date_col] if 'Cash Dividends Paid' in ttm_cash_flow.index else None,
                'common_stock_dividend_paid': ttm_cash_flow.loc['Common Stock Dividend Paid', date_col] if 'Common Stock Dividend Paid' in ttm_cash_flow.index else None,
                'net_common_stock_issuance': ttm_cash_flow.loc['Net Common Stock Issuance', date_col] if 'Net Common Stock Issuance' in ttm_cash_flow.index else None,
                'common_stock_payments': ttm_cash_flow.loc['Common Stock Payments', date_col] if 'Common Stock Payments' in ttm_cash_flow.index else None,
                'net_issuance_payments_of_debt': ttm_cash_flow.loc['Net Issuance Payments Of Debt', date_col] if 'Net Issuance Payments Of Debt' in ttm_cash_flow.index else None,
                'net_short_term_debt_issuance': ttm_cash_flow.loc['Net Short Term Debt Issuance', date_col] if 'Net Short Term Debt Issuance' in ttm_cash_flow.index else None,
                'net_long_term_debt_issuance': ttm_cash_flow.loc['Net Long Term Debt Issuance', date_col] if 'Net Long Term Debt Issuance' in ttm_cash_flow.index else None,
                'long_term_debt_payments': ttm_cash_flow.loc['Long Term Debt Payments', date_col] if 'Long Term Debt Payments' in ttm_cash_flow.index else None,
                'investing_cash_flow': ttm_cash_flow.loc['Investing Cash Flow', date_col] if 'Investing Cash Flow' in ttm_cash_flow.index else None,
                'cash_flow_from_continuing_investing_activities': ttm_cash_flow.loc['Cash Flow From Continuing Investing Activities', date_col] if 'Cash Flow From Continuing Investing Activities' in ttm_cash_flow.index else None,
                'net_other_investing_changes': ttm_cash_flow.loc['Net Other Investing Changes', date_col] if 'Net Other Investing Changes' in ttm_cash_flow.index else None,
                'net_investment_purchase_and_sale': ttm_cash_flow.loc['Net Investment Purchase And Sale', date_col] if 'Net Investment Purchase And Sale' in ttm_cash_flow.index else None,
                'sale_of_investment': ttm_cash_flow.loc['Sale Of Investment', date_col] if 'Sale Of Investment' in ttm_cash_flow.index else None,
                'purchase_of_investment': ttm_cash_flow.loc['Purchase Of Investment', date_col] if 'Purchase Of Investment' in ttm_cash_flow.index else None,
                'net_ppe_purchase_and_sale': ttm_cash_flow.loc['Net PPE Purchase And Sale', date_col] if 'Net PPE Purchase And Sale' in ttm_cash_flow.index else None,
                'purchase_of_ppe': ttm_cash_flow.loc['Purchase Of PPE', date_col] if 'Purchase Of PPE' in ttm_cash_flow.index else None,
                'operating_cash_flow': ttm_cash_flow.loc['Operating Cash Flow', date_col] if 'Operating Cash Flow' in ttm_cash_flow.index else None,
                'cash_flow_from_continuing_operating_activities': ttm_cash_flow.loc['Cash Flow From Continuing Operating Activities', date_col] if 'Cash Flow From Continuing Operating Activities' in ttm_cash_flow.index else None,
                'change_in_working_capital': ttm_cash_flow.loc['Change In Working Capital', date_col] if 'Change In Working Capital' in ttm_cash_flow.index else None,
                'change_in_other_current_liabilities': ttm_cash_flow.loc['Change In Other Current Liabilities', date_col] if 'Change In Other Current Liabilities' in ttm_cash_flow.index else None,
                'change_in_other_current_assets': ttm_cash_flow.loc['Change In Other Current Assets', date_col] if 'Change In Other Current Assets' in ttm_cash_flow.index else None,
                'change_in_payables_and_accrued_expense': ttm_cash_flow.loc['Change In Payables And Accrued Expense', date_col] if 'Change In Payables And Accrued Expense' in ttm_cash_flow.index else None,
                'change_in_payable': ttm_cash_flow.loc['Change In Payable', date_col] if 'Change In Payable' in ttm_cash_flow.index else None,
                'change_in_account_payable': ttm_cash_flow.loc['Change In Account Payable', date_col] if 'Change In Account Payable' in ttm_cash_flow.index else None,
                'change_in_inventory': ttm_cash_flow.loc['Change In Inventory', date_col] if 'Change In Inventory' in ttm_cash_flow.index else None,
                'change_in_receivables': ttm_cash_flow.loc['Change In Receivables', date_col] if 'Change In Receivables' in ttm_cash_flow.index else None,
                'changes_in_account_receivables': ttm_cash_flow.loc['Changes In Account Receivables', date_col] if 'Changes In Account Receivables' in ttm_cash_flow.index else None,
                'other_non_cash_items': ttm_cash_flow.loc['Other Non Cash Items', date_col] if 'Other Non Cash Items' in ttm_cash_flow.index else None,
                'stock_based_compensation': ttm_cash_flow.loc['Stock Based Compensation', date_col] if 'Stock Based Compensation' in ttm_cash_flow.index else None,
                'depreciation_amortization_depletion': ttm_cash_flow.loc['Depreciation Amortization Depletion', date_col] if 'Depreciation Amortization Depletion' in ttm_cash_flow.index else None,
                'depreciation_and_amortization': ttm_cash_flow.loc['Depreciation And Amortization', date_col] if 'Depreciation And Amortization' in ttm_cash_flow.index else None,
                'net_income_from_continuing_operations': ttm_cash_flow.loc['Net Income From Continuing Operations', date_col] if 'Net Income From Continuing Operations' in ttm_cash_flow.index else None
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
            INSERT INTO ttm_cash_flow ({column_names})
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
        logger.error(f"Error loading TTM cash flow data for {symbol}: {e}")
        return 0
    finally:
        if conn:
            conn.close()
        # Clean up memory
        gc.collect()

def main():
    """Main function to load TTM cash flow data for all stocks."""
    try:
        # Create table if it doesn't exist
        create_ttm_cash_flow_table()
        
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
                    records_loaded = load_ttm_cash_flow_for_symbol(symbol)
                    if records_loaded > 0:
                        successful_loads += 1
                        logger.info(f"Successfully loaded {records_loaded} TTM cash flow records for {symbol}")
                    break
                except Exception as e:
                    retries += 1
                    logger.warning(f"Attempt {retries}/{max_retries} failed for {symbol}: {e}")
                    if retries < max_retries:
                        time.sleep(2)  # Wait before retrying
                    else:
                        logger.error(f"Failed to load TTM cash flow data for {symbol} after {max_retries} attempts")
            
            # Sleep to avoid rate limiting
            if i % 5 == 0 and i > 0:
                logger.info(f"Processed {i} symbols. Taking a short break...")
                time.sleep(1)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        logger.info(f"TTM cash flow data loading completed. Successfully loaded data for {successful_loads}/{len(symbols)} symbols in {elapsed_time:.2f} seconds")
        
    except Exception as e:
        logger.error(f"Error in main process: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
