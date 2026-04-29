#!/usr/bin/env python3
# Triggered: 2026-04-28 14:50 UTC - Batch 4 Financial Statements
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
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

SCRIPT_NAME = "loadannualbalancesheet.py"
REQUEST_DELAY = 0.5

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

            # If it's a DNS/network error and we're on RDS, try localhost as fallback
            if attempt < max_retries - 1:
                if "could not translate host" in error_msg or "refused" in error_msg:
                    if "rds-stocks" in db_host:
                        logging.info("RDS unreachable - will retry")
                        time.sleep((attempt + 1) * 2)  # exponential backoff
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
    """Create required tables if they don't exist - Dynamic schema to capture all yfinance fields"""
    try:
        # Create table with expanded columns matching quarterly_balance_sheet comprehensiveness
        create_stmt = """
        CREATE TABLE IF NOT EXISTS annual_balance_sheet (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            date DATE,
            treasury_shares_number NUMERIC,
            ordinary_shares_number NUMERIC,
            share_issued NUMERIC,
            net_debt DECIMAL(16,2),
            total_debt DECIMAL(16,2),
            tangible_book_value DECIMAL(16,2),
            invested_capital DECIMAL(16,2),
            working_capital DECIMAL(16,2),
            net_tangible_assets DECIMAL(16,2),
            capital_lease_obligations DECIMAL(16,2),
            common_stock_equity DECIMAL(16,2),
            total_capitalization DECIMAL(16,2),
            total_equity_gross_minority_interest DECIMAL(16,2),
            stockholders_equity DECIMAL(16,2),
            gains_losses_not_affecting_retained_earnings DECIMAL(16,2),
            other_equity_adjustments DECIMAL(16,2),
            retained_earnings DECIMAL(16,2),
            capital_stock DECIMAL(16,2),
            common_stock DECIMAL(16,2),
            total_liabilities_net_minority_interest DECIMAL(16,2),
            total_non_current_liabilities_net_minority_interest DECIMAL(16,2),
            other_non_current_liabilities DECIMAL(16,2),
            tradeand_other_payables_non_current DECIMAL(16,2),
            long_term_debt_and_capital_lease_obligation DECIMAL(16,2),
            long_term_capital_lease_obligation DECIMAL(16,2),
            long_term_debt DECIMAL(16,2),
            current_liabilities DECIMAL(16,2),
            other_current_liabilities DECIMAL(16,2),
            current_deferred_liabilities DECIMAL(16,2),
            current_deferred_revenue DECIMAL(16,2),
            current_debt_and_capital_lease_obligation DECIMAL(16,2),
            current_capital_lease_obligation DECIMAL(16,2),
            current_debt DECIMAL(16,2),
            other_current_borrowings DECIMAL(16,2),
            commercial_paper DECIMAL(16,2),
            payables_and_accrued_expenses DECIMAL(16,2),
            current_accrued_expenses DECIMAL(16,2),
            payables DECIMAL(16,2),
            total_tax_payable DECIMAL(16,2),
            income_tax_payable DECIMAL(16,2),
            accounts_payable DECIMAL(16,2),
            total_non_current_assets DECIMAL(16,2),
            other_non_current_assets DECIMAL(16,2),
            non_current_deferred_assets DECIMAL(16,2),
            non_current_deferred_taxes_assets DECIMAL(16,2),
            investments_and_advances DECIMAL(16,2),
            other_investments DECIMAL(16,2),
            investmentin_financial_assets DECIMAL(16,2),
            available_for_sale_securities DECIMAL(16,2),
            net_ppe DECIMAL(16,2),
            accumulated_depreciation DECIMAL(16,2),
            gross_ppe DECIMAL(16,2),
            leases DECIMAL(16,2),
            other_properties DECIMAL(16,2),
            machinery_furniture_equipment DECIMAL(16,2),
            land_and_improvements DECIMAL(16,2),
            properties DECIMAL(16,2),
            current_assets DECIMAL(16,2),
            other_current_assets DECIMAL(16,2),
            inventory DECIMAL(16,2),
            receivables DECIMAL(16,2),
            other_receivables DECIMAL(16,2),
            accounts_receivable DECIMAL(16,2),
            cash_cash_equivalents_and_short_term_investments DECIMAL(16,2),
            other_short_term_investments DECIMAL(16,2),
            cash_and_cash_equivalents DECIMAL(16,2),
            cash_equivalents DECIMAL(16,2),
            total_assets DECIMAL(16,2),
            total_liabilities DECIMAL(16,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, fiscal_year)
        )
        """
        cur.execute(create_stmt)
        logging.info("Created annual_balance_sheet with full 75+ column schema to capture all yfinance data")
    except Exception as e:
        logging.error(f"Error creating table: {e}")

def load_balance_sheet_for_symbol(cur, symbol: str, attempt: int = 0) -> int:
    """Load annual balance sheet for a single symbol - captures ALL yfinance fields"""
    try:
        yf_symbol = symbol.replace(".", "-").upper()

        time.sleep(REQUEST_DELAY)

        ticker = yf.Ticker(yf_symbol)

        # Try to get annual balance sheet
        try:
            balance_sheet = ticker.balance_sheet
            if balance_sheet is None or balance_sheet.empty:
                return 0
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < 3:
                wait_time = (2 ** attempt) * 5
                logging.warning(f"{symbol}: Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                return load_balance_sheet_for_symbol(cur, symbol, attempt + 1)
            return 0
        except Exception:
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

                # Check for required field
                total_assets = safe_convert_to_float(row_data.get('Total Assets'))
                if total_assets is None:
                    continue

                # Extract ALL available fields from yfinance balance sheet
                # Use yfinance column names mapped to our database columns
                field_mapping = {
                    'Treasury Shares Number': 'treasury_shares_number',
                    'Ordinary Shares Number': 'ordinary_shares_number',
                    'Share Issued': 'share_issued',
                    'Net Debt': 'net_debt',
                    'Total Debt': 'total_debt',
                    'Tangible Book Value': 'tangible_book_value',
                    'Invested Capital': 'invested_capital',
                    'Working Capital': 'working_capital',
                    'Net Tangible Assets': 'net_tangible_assets',
                    'Capital Lease Obligations': 'capital_lease_obligations',
                    'Common Stock Equity': 'common_stock_equity',
                    'Total Capitalization': 'total_capitalization',
                    'Total Equity Gross Minority Interest': 'total_equity_gross_minority_interest',
                    'Stockholders Equity': 'stockholders_equity',
                    'Gains Losses Not Affecting Retained Earnings': 'gains_losses_not_affecting_retained_earnings',
                    'Other Equity Adjustments': 'other_equity_adjustments',
                    'Retained Earnings': 'retained_earnings',
                    'Capital Stock': 'capital_stock',
                    'Common Stock': 'common_stock',
                    'Total Liabilities Net Minority Interest': 'total_liabilities_net_minority_interest',
                    'Total Non Current Liabilities Net Minority Interest': 'total_non_current_liabilities_net_minority_interest',
                    'Other Non Current Liabilities': 'other_non_current_liabilities',
                    'Tradeand Other Payables Non Current': 'tradeand_other_payables_non_current',
                    'Long Term Debt And Capital Lease Obligation': 'long_term_debt_and_capital_lease_obligation',
                    'Long Term Capital Lease Obligation': 'long_term_capital_lease_obligation',
                    'Long Term Debt': 'long_term_debt',
                    'Current Liabilities': 'current_liabilities',
                    'Other Current Liabilities': 'other_current_liabilities',
                    'Current Deferred Liabilities': 'current_deferred_liabilities',
                    'Current Deferred Revenue': 'current_deferred_revenue',
                    'Current Debt And Capital Lease Obligation': 'current_debt_and_capital_lease_obligation',
                    'Current Capital Lease Obligation': 'current_capital_lease_obligation',
                    'Current Debt': 'current_debt',
                    'Other Current Borrowings': 'other_current_borrowings',
                    'Commercial Paper': 'commercial_paper',
                    'Payables And Accrued Expenses': 'payables_and_accrued_expenses',
                    'Current Accrued Expenses': 'current_accrued_expenses',
                    'Payables': 'payables',
                    'Total Tax Payable': 'total_tax_payable',
                    'Income Tax Payable': 'income_tax_payable',
                    'Accounts Payable': 'accounts_payable',
                    'Total Non Current Assets': 'total_non_current_assets',
                    'Other Non Current Assets': 'other_non_current_assets',
                    'Non Current Deferred Assets': 'non_current_deferred_assets',
                    'Non Current Deferred Taxes Assets': 'non_current_deferred_taxes_assets',
                    'Investments And Advances': 'investments_and_advances',
                    'Other Investments': 'other_investments',
                    'Investmentin Financial Assets': 'investmentin_financial_assets',
                    'Available For Sale Securities': 'available_for_sale_securities',
                    'Net Ppe': 'net_ppe',
                    'Accumulated Depreciation': 'accumulated_depreciation',
                    'Gross Ppe': 'gross_ppe',
                    'Leases': 'leases',
                    'Other Properties': 'other_properties',
                    'Machinery Furniture Equipment': 'machinery_furniture_equipment',
                    'Land And Improvements': 'land_and_improvements',
                    'Properties': 'properties',
                    'Current Assets': 'current_assets',
                    'Other Current Assets': 'other_current_assets',
                    'Inventory': 'inventory',
                    'Receivables': 'receivables',
                    'Other Receivables': 'other_receivables',
                    'Accounts Receivable': 'accounts_receivable',
                    'Cash Cash Equivalents And Short Term Investments': 'cash_cash_equivalents_and_short_term_investments',
                    'Other Short Term Investments': 'other_short_term_investments',
                    'Cash And Cash Equivalents': 'cash_and_cash_equivalents',
                    'Cash Equivalents': 'cash_equivalents',
                    'Total Assets': 'total_assets',
                    'Total Liabilities': 'total_liabilities'
                }

                # Build values dict by extracting from yfinance data
                values_dict = {'symbol': symbol, 'fiscal_year': fiscal_year, 'date': fiscal_date.date() if fiscal_date else None}
                for yf_field, db_col in field_mapping.items():
                    values_dict[db_col] = safe_convert_to_float(row_data.get(yf_field))

                # Build INSERT statement dynamically with all available fields
                cols = ', '.join(values_dict.keys())
                placeholders = ', '.join(['%s'] * len(values_dict))
                values = list(values_dict.values())

                cur.execute(f"""
                    INSERT INTO annual_balance_sheet ({cols})
                    VALUES ({placeholders})
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                    total_assets = EXCLUDED.total_assets,
                    updated_at = NOW()
                """, values)
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

        cur.execute("""
            SELECT DISTINCT ss.symbol FROM stock_symbols ss
            WHERE NOT EXISTS (
                SELECT 1 FROM annual_balance_sheet t WHERE t.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)
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
        logging.info(f"Completed: {total_rows} rows inserted, {successful} successful")
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
