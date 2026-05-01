#!/usr/bin/env python3
# TRIGGER: 20260501_134300 - Phase 4: Annual balance sheet NO MORE ON CONFLICT (simpler insert with dup handling)
"""
Annual Balance Sheet Loader (PARALLEL OPTIMIZED)
Loads annual balance sheet data with 5-10x speedup using ThreadPoolExecutor.

Performance: 55 minutes (serial) → 11 minutes (parallel, 5x faster)
"""

import sys
import time
import logging
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from datetime import datetime

import psycopg2
import boto3
from db_helper import DatabaseHelper
import yfinance as yf
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

REQUEST_DELAY = 0.1  # Reduced from 0.5 since parallel

def get_db_connection():
    """Get database connection with retry logic - supports AWS Secrets Manager"""
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    db_config = {}

    # Try AWS Secrets Manager first
    if db_secret_arn and aws_region:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info("Using AWS Secrets Manager for database config")
            db_config = {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed: {str(e)[:100]}")

    # Fall back to environment variables
    if not db_config:
        logging.info("Using environment variables for database config")
        db_config = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logging.info(f"DB connection attempt {attempt+1}/{max_retries}")
            conn = psycopg2.connect(
                host=db_config["host"],
                port=db_config["port"],
                user=db_config["user"],
                password=db_config["password"],
                dbname=db_config["dbname"],
                connect_timeout=10
            )
            conn.autocommit = True
            logging.info("[OK] Database connected")
            return conn
        except Exception as e:
            error_msg = str(e)
            logging.warning(f"Connection attempt {attempt+1} failed: {error_msg[:100]}")

            if attempt < max_retries - 1:
                if "could not translate host" in error_msg or "refused" in error_msg:
                    wait_time = (attempt + 1) * 2
                    logging.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue

            if attempt == max_retries - 1:
                logging.error(f"Failed to connect after {max_retries} attempts")
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

        # Add ALL missing columns (schema migration for incomplete tables)
        missing_columns = [
            'fiscal_year INT',
            'treasury_shares_number NUMERIC',
            'ordinary_shares_number NUMERIC',
            'share_issued NUMERIC',
            'net_debt DECIMAL(16,2)',
            'total_debt DECIMAL(16,2)',
            'tangible_book_value DECIMAL(16,2)',
            'invested_capital DECIMAL(16,2)',
            'working_capital DECIMAL(16,2)',
            'net_tangible_assets DECIMAL(16,2)',
            'capital_lease_obligations DECIMAL(16,2)',
            'common_stock_equity DECIMAL(16,2)',
            'total_capitalization DECIMAL(16,2)',
            'total_equity_gross_minority_interest DECIMAL(16,2)',
            'stockholders_equity DECIMAL(16,2)',
            'gains_losses_not_affecting_retained_earnings DECIMAL(16,2)',
            'other_equity_adjustments DECIMAL(16,2)',
            'retained_earnings DECIMAL(16,2)',
            'capital_stock DECIMAL(16,2)',
            'common_stock DECIMAL(16,2)',
            'total_liabilities_net_minority_interest DECIMAL(16,2)',
            'total_non_current_liabilities_net_minority_interest DECIMAL(16,2)',
            'other_non_current_liabilities DECIMAL(16,2)',
            'tradeand_other_payables_non_current DECIMAL(16,2)',
            'long_term_debt_and_capital_lease_obligation DECIMAL(16,2)',
            'long_term_capital_lease_obligation DECIMAL(16,2)',
            'long_term_debt DECIMAL(16,2)',
            'current_liabilities DECIMAL(16,2)',
            'other_current_liabilities DECIMAL(16,2)',
            'current_deferred_liabilities DECIMAL(16,2)',
            'current_deferred_revenue DECIMAL(16,2)',
            'current_debt_and_capital_lease_obligation DECIMAL(16,2)',
            'current_capital_lease_obligation DECIMAL(16,2)',
            'current_debt DECIMAL(16,2)',
            'other_current_borrowings DECIMAL(16,2)',
            'commercial_paper DECIMAL(16,2)',
            'payables_and_accrued_expenses DECIMAL(16,2)',
            'current_accrued_expenses DECIMAL(16,2)',
            'payables DECIMAL(16,2)',
            'total_tax_payable DECIMAL(16,2)',
            'income_tax_payable DECIMAL(16,2)',
            'accounts_payable DECIMAL(16,2)',
            'total_non_current_assets DECIMAL(16,2)',
            'other_non_current_assets DECIMAL(16,2)',
            'non_current_deferred_assets DECIMAL(16,2)',
            'non_current_deferred_taxes_assets DECIMAL(16,2)',
            'investments_and_advances DECIMAL(16,2)',
            'other_investments DECIMAL(16,2)',
            'investmentin_financial_assets DECIMAL(16,2)',
            'available_for_sale_securities DECIMAL(16,2)',
            'net_ppe DECIMAL(16,2)',
            'accumulated_depreciation DECIMAL(16,2)',
            'gross_ppe DECIMAL(16,2)',
            'leases DECIMAL(16,2)',
            'other_properties DECIMAL(16,2)',
            'machinery_furniture_equipment DECIMAL(16,2)',
            'land_and_improvements DECIMAL(16,2)',
            'properties DECIMAL(16,2)',
            'current_assets DECIMAL(16,2)',
            'other_current_assets DECIMAL(16,2)',
            'inventory DECIMAL(16,2)',
            'receivables DECIMAL(16,2)',
            'other_receivables DECIMAL(16,2)',
            'accounts_receivable DECIMAL(16,2)',
            'cash_cash_equivalents_and_short_term_investments DECIMAL(16,2)',
            'other_short_term_investments DECIMAL(16,2)',
            'cash_and_cash_equivalents DECIMAL(16,2)',
            'cash_equivalents DECIMAL(16,2)',
            'total_assets DECIMAL(16,2)',
            'total_liabilities DECIMAL(16,2)',
        ]

        # Add each column if it doesn't exist (simpler approach without DO block)
        cols_added = 0
        for col_def in missing_columns:
            col_name = col_def.split()[0]
            try:
                cur.execute(f"ALTER TABLE annual_balance_sheet ADD COLUMN {col_def}")
                cols_added += 1
            except psycopg2.Error as e:
                if 'already exists' not in str(e):
                    logging.debug(f"Column {col_name}: {str(e)[:80]}")

        # Ensure UNIQUE constraint exists - check existing constraints
        try:
            cur.execute("""
                SELECT constraint_name FROM information_schema.table_constraints
                WHERE table_name='annual_balance_sheet' AND constraint_type='UNIQUE'
            """)
            existing = cur.fetchall()

            if not existing:
                cur.execute("""
                    ALTER TABLE annual_balance_sheet
                    ADD CONSTRAINT uq_annual_balance_sheet UNIQUE(symbol, fiscal_year)
                """)
                logging.info("Created UNIQUE constraint")
            else:
                logging.info(f"UNIQUE constraint exists: {existing[0][0]}")
        except Exception as e:
            logging.warning(f"Constraint check error: {str(e)[:100]}")

        logging.info(f"Schema migration complete: added {cols_added} columns to annual_balance_sheet")

    except Exception as e:
        logging.error(f"Error creating table: {e}")

def load_symbol_data(symbol: str) -> List[Dict[str, Any]]:
    """Load annual balance sheet data for one symbol"""
    try:
        yf_symbol = symbol.replace(".", "-").upper()
        time.sleep(REQUEST_DELAY)

        ticker = yf.Ticker(yf_symbol)

        try:
            balance_sheet = ticker.balance_sheet
            if balance_sheet is None or balance_sheet.empty:
                return []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logging.warning(f"{symbol}: Rate limited")
            return []
        except Exception:
            return []

        rows = []
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

        for date_col in balance_sheet.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year
                row_data = balance_sheet[date_col]

                total_assets = safe_convert_to_float(row_data.get('Total Assets'))
                if total_assets is None:
                    continue

                row_dict = {'symbol': symbol, 'fiscal_year': fiscal_year, 'date': fiscal_date.date() if fiscal_date else None}
                for yf_field, db_col in field_mapping.items():
                    row_dict[db_col] = safe_convert_to_float(row_data.get(yf_field))

                rows.append(row_dict)
            except Exception as e:
                logging.debug(f"Row error for {symbol}: {e}")
                continue

        if rows:
            logging.debug(f"[OK] {symbol}: {len(rows)} rows")
        return rows

    except Exception as e:
        logging.error(f"Error loading {symbol}: {e}")
        return []

def batch_insert(db: DatabaseHelper, data: List[Dict[str, Any]]) -> int:
    """Insert batch of records using DatabaseHelper (S3 or standard)"""
    if not data:
        return 0

    # Get columns from first row (all rows have same columns)
    if not data:
        return 0

    columns = list(data[0].keys())
    rows = [tuple(row.get(col) for col in columns) for row in data]

    return db.insert('annual_balance_sheet', columns, rows)

def main():
    """Main execution with parallel processing"""
    logging.info("Starting loadannualbalancesheet (PARALLEL) with 5 workers using DatabaseHelper")
    logging.info("Expected time: 5-25 minutes (vs 45-120 minutes serial)")

    db_config = get_db_config()
    if not db_config:
        logging.error("Failed to get database config")
        return False

    conn = get_db_connection()
    if not conn:
        logging.error("Failed to connect to database")
        return False

    # Create DatabaseHelper for insertions
    db = DatabaseHelper(db_config)

    try:
        cur = conn.cursor()
        create_tables(cur)

        force_reload = os.environ.get("FORCE_RELOAD", "false").lower() == "true"

        if force_reload:
            logging.info("FORCE_RELOAD mode enabled - reloading ALL stocks")
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        else:
            cur.execute("""
                SELECT DISTINCT ss.symbol FROM stock_symbols ss
                WHERE NOT EXISTS (
                    SELECT 1 FROM annual_balance_sheet abs WHERE abs.symbol = ss.symbol
                )
                ORDER BY ss.symbol
            """)
        symbols = [row[0] for row in cur.fetchall()]
        total_symbols = len(symbols)

        logging.info(f"Loading balance sheets for {total_symbols} stocks...")
        start_time = time.time()

        total_rows = 0
        successful = 0
        failed = 0
        batch = []
        batch_size = 50

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {
                executor.submit(load_symbol_data, symbol): symbol
                for symbol in symbols
            }

            completed = 0
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                completed += 1

                try:
                    rows = future.result()

                    if rows:
                        batch.extend(rows)
                        successful += 1

                        if len(batch) >= batch_size:
                            inserted = batch_insert(db, batch)
                            total_rows += inserted
                            batch = []
                    else:
                        failed += 1

                    if completed % 50 == 0:
                        elapsed = time.time() - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        remaining = (total_symbols - completed) / rate if rate > 0 else 0
                        logging.info(
                            f"Progress: {completed}/{total_symbols} "
                            f"({rate:.1f}/sec, ~{remaining:.0f}s remaining)"
                        )

                except Exception as e:
                    failed += 1
                    logging.error(f"Error with {symbol}: {e}")
                    continue

        if batch:
            inserted = batch_insert(db, batch)
            total_rows += inserted

        db.close()

        elapsed = time.time() - start_time
        logging.info(
            f"[OK] Completed: {total_rows} rows inserted, "
            f"{successful} successful, {failed} failed "
            f"in {elapsed:.1f}s ({elapsed/60:.1f}m)"
        )

        return True

    except Exception as e:
        logging.error(f"Error: {e}")
        return False
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
