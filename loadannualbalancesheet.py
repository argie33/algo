#!/usr/bin/env python3
"""
Annual Balance Sheet Loader
Loads annual balance sheet data for all stocks from yfinance
Part of comprehensive AWS-compatible real data loading system
"""

import sys
import time
import logging
import os
from datetime import datetime, date
from typing import Optional

import psycopg2
import yfinance as yf
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

SCRIPT_NAME = "loadannualbalancesheet.py"

def get_db_connection():
    """Get database connection from environment variables"""
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            user=os.environ.get("DB_USER", "stocks"),
            password=os.environ.get("DB_PASSWORD", ""),
            dbname=os.environ.get("DB_NAME", "stocks"),
            connect_timeout=10
        )
        conn.autocommit = True
        return conn
    except Exception as e:
        logging.error(f"Failed to connect to database: {e}")
        return None

def safe_convert_to_float(value) -> Optional[float]:
    """Safely convert value to float"""
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
            if value == '' or value == '-' or value.lower() == 'n/a':
                return None
        return float(value)
    except (ValueError, TypeError):
        return None

def create_tables(cur):
    """Create required tables if they don't exist"""
    create_statements = [
        """
        CREATE TABLE IF NOT EXISTS annual_balance_sheet (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            date DATE,
            total_assets DECIMAL(16,2),
            current_assets DECIMAL(16,2),
            total_liabilities DECIMAL(16,2),
            current_liabilities DECIMAL(16,2),
            stockholders_equity DECIMAL(16,2),
            cash_and_equivalents DECIMAL(16,2),
            accounts_receivable DECIMAL(16,2),
            inventory DECIMAL(16,2),
            accounts_payable DECIMAL(16,2),
            long_term_debt DECIMAL(16,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, fiscal_year)
        )
        """
    ]

    for stmt in create_statements:
        try:
            cur.execute(stmt)
            logging.info("Created/verified table structure")
        except Exception as e:
            logging.error(f"Error creating table: {e}")

def load_balance_sheet_for_symbol(cur, symbol: str) -> int:
    """Load annual balance sheet for a single symbol"""
    try:
        yf_symbol = symbol.replace(".", "-").upper()
        ticker = yf.Ticker(yf_symbol)

        # Try to get annual balance sheet
        try:
            balance_sheet = ticker.balance_sheet
            if balance_sheet is None or balance_sheet.empty:
                balance_sheet = ticker.quarterly_balance_sheet
                if balance_sheet is None or balance_sheet.empty:
                    return 0
        except:
            return 0

        if balance_sheet is None or balance_sheet.empty:
            logging.warning(f"No annual balance sheet data for {symbol}")
            return 0

        rows_inserted = 0

        # Process each fiscal year
        for date_col in balance_sheet.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year

                row_data = balance_sheet[date_col]

                # Extract key metrics
                total_assets = safe_convert_to_float(row_data.get('Total Assets'))
                current_assets = safe_convert_to_float(row_data.get('Current Assets'))
                total_liabilities = safe_convert_to_float(row_data.get('Total Liabilities Net Minority Interest'))
                current_liabilities = safe_convert_to_float(row_data.get('Current Liabilities'))
                stockholders_equity = safe_convert_to_float(row_data.get('Stockholders Equity'))
                cash = safe_convert_to_float(row_data.get('Cash And Cash Equivalents'))
                ar = safe_convert_to_float(row_data.get('Accounts Receivable'))
                inventory = safe_convert_to_float(row_data.get('Inventory'))
                ap = safe_convert_to_float(row_data.get('Accounts Payable'))
                lt_debt = safe_convert_to_float(row_data.get('Long Term Debt'))

                # Skip if no total assets
                if total_assets is None:
                    continue

                # Insert or update
                cur.execute("""
                    INSERT INTO annual_balance_sheet
                    (symbol, fiscal_year, date, total_assets, current_assets, total_liabilities,
                     current_liabilities, stockholders_equity, cash_and_equivalents, accounts_receivable,
                     inventory, accounts_payable, long_term_debt, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                    total_assets = EXCLUDED.total_assets,
                    current_assets = EXCLUDED.current_assets,
                    total_liabilities = EXCLUDED.total_liabilities,
                    current_liabilities = EXCLUDED.current_liabilities,
                    stockholders_equity = EXCLUDED.stockholders_equity,
                    cash_and_equivalents = EXCLUDED.cash_and_equivalents,
                    accounts_receivable = EXCLUDED.accounts_receivable,
                    inventory = EXCLUDED.inventory,
                    accounts_payable = EXCLUDED.accounts_payable,
                    long_term_debt = EXCLUDED.long_term_debt,
                    updated_at = NOW()
                """, (
                    symbol, fiscal_year, fiscal_date.date() if fiscal_date else None,
                    total_assets, current_assets, total_liabilities,
                    current_liabilities, stockholders_equity, cash,
                    ar, inventory, ap, lt_debt
                ))
                rows_inserted += 1

            except Exception as e:
                logging.debug(f"Error processing row for {symbol}: {e}")
                continue

        return rows_inserted

    except Exception as e:
        logging.error(f"Error loading balance sheet for {symbol}: {e}")
        return 0

def main():
    """Main loader function"""
    logging.info(f"Starting {SCRIPT_NAME}")

    conn = get_db_connection()
    if not conn:
        logging.error("Failed to connect to database")
        return False

    try:
        cur = conn.cursor()
        create_tables(cur)

        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Loading balance sheets for {len(symbols)} stocks...")

        total_rows = 0
        successful = 0

        for i, symbol in enumerate(symbols):
            logging.info(f"[{i+1}/{len(symbols)}] Loading {symbol}...")
            rows = load_balance_sheet_for_symbol(cur, symbol)
            total_rows += rows
            if rows > 0:
                successful += 1

            if (i + 1) % 10 == 0:
                conn.commit()

        conn.commit()
        logging.info(f"✓ Completed: {total_rows} rows inserted, {successful} successful")
        return True

    except Exception as e:
        logging.error(f"Error in main: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
