#!/usr/bin/env python3
# Triggered: 2026-04-28 14:50 UTC - Batch 4 Financial Statements
"""
Annual Income Statement Loader
Loads annual income statement data for all stocks from yfinance
Part of comprehensive AWS-compatible real data loading system
"""

import sys
import time
import logging
import json
import os
import gc
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False
from datetime import datetime, date
from typing import List, Tuple, Optional

import psycopg2
from psycopg2.extras import execute_values
import boto3
import yfinance as yf
import pandas as pd
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

SCRIPT_NAME = "loadannualincomestatement.py"
REQUEST_DELAY = 0.5  # delay between yfinance requests to avoid rate limiting

def get_db_connection():
    """Get database connection from environment variables with retries"""
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", "5432"))
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempting database connection (attempt {attempt+1}/{max_retries}): {db_host}:{db_port}")
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                dbname=db_name,
                connect_timeout=10
            )
            conn.autocommit = True
            logging.info("Database connection successful")
            return conn
        except Exception as e:
            error_msg = str(e)
            logging.warning(f"Connection attempt {attempt+1} failed: {error_msg[:100]}")

            if attempt < max_retries - 1:
                if "could not translate host" in error_msg or "refused" in error_msg:
                    if "rds-stocks" in db_host:
                        logging.info("RDS unreachable - will retry")
                        time.sleep((attempt + 1) * 2)
                        continue

            if attempt == max_retries - 1:
                logging.error(f"Failed to connect to database after {max_retries} attempts: {error_msg}")
                return None

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
        CREATE TABLE IF NOT EXISTS annual_income_statement (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            date DATE,
            revenue DECIMAL(16,2),
            cost_of_revenue DECIMAL(16,2),
            gross_profit DECIMAL(16,2),
            operating_expenses DECIMAL(16,2),
            operating_income DECIMAL(16,2),
            net_income DECIMAL(16,2),
            earnings_per_share DECIMAL(12,4),
            tax_expense DECIMAL(16,2),
            interest_expense DECIMAL(16,2),
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

def load_income_statement_for_symbol(cur, symbol: str, attempt: int = 0) -> int:
    """Load annual income statement for a single symbol"""
    try:
        yf_symbol = symbol.replace(".", "-").upper()

        # Add delay to avoid rate limiting
        time.sleep(REQUEST_DELAY)

        ticker = yf.Ticker(yf_symbol)

        # Try to get annual income statement
        try:
            income_stmt = ticker.income_stmt
            if income_stmt is None or income_stmt.empty:
                income_stmt = ticker.financials
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < 3:
                wait_time = (2 ** attempt) * 5  # exponential backoff: 5s, 10s, 20s
                logging.warning(f"{symbol}: Rate limited, waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                return load_income_statement_for_symbol(cur, symbol, attempt + 1)
            income_stmt = ticker.financials
        except Exception:
            income_stmt = ticker.financials

        if income_stmt is None or income_stmt.empty:
            logging.debug(f"No data for {symbol}")
            return 0

        rows_inserted = 0

        # Process each fiscal year (columns are dates)
        for date_col in income_stmt.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year

                row_data = income_stmt[date_col]

                # Extract key metrics
                revenue = safe_convert_to_float(row_data.get('Total Revenue'))
                cost_of_revenue = safe_convert_to_float(row_data.get('Cost Of Revenue'))
                gross_profit = safe_convert_to_float(row_data.get('Gross Profit'))
                operating_expenses = safe_convert_to_float(row_data.get('Operating Expense'))
                operating_income = safe_convert_to_float(row_data.get('Operating Income'))
                net_income = safe_convert_to_float(row_data.get('Net Income'))
                tax_expense = safe_convert_to_float(row_data.get('Income Tax Expense'))
                interest_expense = safe_convert_to_float(row_data.get('Interest Expense'))

                # Skip if no revenue (invalid record)
                if revenue is None:
                    continue

                # Insert or update — use actual DB column names
                cur.execute("""
                    INSERT INTO annual_income_statement
                    (symbol, fiscal_year, revenue, cost_of_revenue, gross_profit,
                     operating_expenses, operating_income, net_income, tax_provision, interest_expense)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                    revenue = EXCLUDED.revenue,
                    cost_of_revenue = EXCLUDED.cost_of_revenue,
                    gross_profit = EXCLUDED.gross_profit,
                    operating_expenses = EXCLUDED.operating_expenses,
                    operating_income = EXCLUDED.operating_income,
                    net_income = EXCLUDED.net_income,
                    tax_provision = EXCLUDED.tax_provision,
                    interest_expense = EXCLUDED.interest_expense
                """, (
                    symbol, fiscal_year,
                    revenue, cost_of_revenue, gross_profit,
                    operating_expenses, operating_income, net_income,
                    tax_expense, interest_expense
                ))
                rows_inserted += 1

            except Exception as e:
                logging.debug(f"Error processing row for {symbol}: {e}")
                continue

        return rows_inserted

    except Exception as e:
        logging.error(f"Error loading income statement for {symbol}: {e}")
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

        # Create tables
        create_tables(cur)

        # Get all stock symbols — skip those already loaded to avoid re-fetching
        cur.execute("""
            SELECT DISTINCT ss.symbol FROM stock_symbols ss
            WHERE NOT EXISTS (
                SELECT 1 FROM annual_income_statement ais WHERE ais.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Loading income statements for {len(symbols)} remaining stocks...")

        total_rows = 0
        successful = 0
        failed = 0

        for i, symbol in enumerate(symbols):
            logging.info(f"[{i+1}/{len(symbols)}] Loading {symbol}...")
            rows = load_income_statement_for_symbol(cur, symbol)
            total_rows += rows

            if rows > 0:
                successful += 1
            else:
                failed += 1

            # Periodic commit
            if (i + 1) % 10 == 0:
                conn.commit()

        conn.commit()
        logging.info(f"Completed: {total_rows} rows inserted, {successful} successful, {failed} failed")
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
