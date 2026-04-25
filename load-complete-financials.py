#!/usr/bin/env python3
"""
Complete Financial Statement Loader - Loads ALL yfinance columns into database
"""

import os
import sys
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf
import pandas as pd

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def normalize_column_name(name: str) -> str:
    """Convert yfinance column name to SQL column name"""
    return name.lower().replace(" ", "_").replace("/", "").replace("&", "and").replace("-", "_").replace("(", "").replace(")", "")

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", 5432),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME", "stocks")
    )

def safe_int(val) -> Optional[int]:
    """Safely convert value to int"""
    if val is None or pd.isna(val):
        return None
    try:
        return int(float(val))
    except:
        return None

def load_balance_sheet(symbol: str, period: str = "annual"):
    """Load balance sheet data for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        bs = ticker.balance_sheet if period == "annual" else ticker.quarterly_balance_sheet

        if bs is None or len(bs) == 0:
            return None

        records = []
        for date, row in bs.items():
            fiscal_year = date.year
            record = {
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": None,
                "date": date,
            }

            for col_name in bs.index:
                value = row.get(col_name)
                sql_col_name = normalize_column_name(col_name)
                record[sql_col_name] = safe_int(value)

            records.append(record)

        return records

    except Exception as e:
        logging.warning(f"Failed to load balance sheet for {symbol}: {str(e)[:100]}")
        return None

def load_income_statement(symbol: str, period: str = "annual"):
    """Load income statement data for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        income = ticker.income_stmt if period == "annual" else ticker.quarterly_income_stmt

        if income is None or len(income) == 0:
            return None

        records = []
        for date, row in income.items():
            fiscal_year = date.year
            record = {
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": None,
                "date": date,
            }

            for col_name in income.index:
                value = row.get(col_name)
                sql_col_name = normalize_column_name(col_name)
                record[sql_col_name] = safe_int(value)

            records.append(record)

        return records

    except Exception as e:
        logging.warning(f"Failed to load income statement for {symbol}: {str(e)[:100]}")
        return None

def load_cash_flow(symbol: str, period: str = "annual"):
    """Load cash flow data for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        cf = ticker.cashflow if period == "annual" else ticker.quarterly_cashflow

        if cf is None or len(cf) == 0:
            return None

        records = []
        for date, row in cf.items():
            fiscal_year = date.year
            record = {
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": None,
                "date": date,
            }

            for col_name in cf.index:
                value = row.get(col_name)
                sql_col_name = normalize_column_name(col_name)
                record[sql_col_name] = safe_int(value)

            records.append(record)

        return records

    except Exception as e:
        logging.warning(f"Failed to load cash flow for {symbol}: {str(e)[:100]}")
        return None

def insert_balance_sheet(conn, records: List[Dict], period: str = "annual"):
    """Insert balance sheet records into database"""
    if not records:
        return 0

    table_name = "annual_balance_sheet" if period == "annual" else "quarterly_balance_sheet"
    cur = conn.cursor()

    try:
        columns = list(records[0].keys())
        # Remove fiscal_quarter for annual statements, and date
        columns = [col for col in columns if col not in ['date'] and (period == "quarterly" or col != 'fiscal_quarter')]

        placeholders = ",".join(["%s"] * len(columns))
        column_list = ",".join(columns)

        values = []
        for record in records:
            row = tuple(record.get(col) for col in columns)
            values.append(row)

        sql = f"""
            INSERT INTO {table_name} ({column_list})
            VALUES %s
            ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                {', '.join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
        """

        execute_values(cur, sql, values)
        conn.commit()
        return len(values)

    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert balance sheet: {str(e)[:200]}")
        return 0
    finally:
        cur.close()

def insert_income_statement(conn, records: List[Dict], period: str = "annual"):
    """Insert income statement records into database"""
    if not records:
        return 0

    table_name = "annual_income_statement" if period == "annual" else "quarterly_income_statement"
    cur = conn.cursor()

    try:
        columns = list(records[0].keys())
        # Remove fiscal_quarter for annual statements, and date
        columns = [col for col in columns if col not in ['date'] and (period == "quarterly" or col != 'fiscal_quarter')]

        placeholders = ",".join(["%s"] * len(columns))
        column_list = ",".join(columns)

        values = []
        for record in records:
            row = tuple(record.get(col) for col in columns)
            values.append(row)

        sql = f"""
            INSERT INTO {table_name} ({column_list})
            VALUES %s
            ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                {', '.join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
        """

        execute_values(cur, sql, values)
        conn.commit()
        return len(values)

    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert income statement: {str(e)[:200]}")
        return 0
    finally:
        cur.close()

def insert_cash_flow(conn, records: List[Dict], period: str = "annual"):
    """Insert cash flow records into database"""
    if not records:
        return 0

    table_name = "annual_cash_flow" if period == "annual" else "quarterly_cash_flow"
    cur = conn.cursor()

    try:
        columns = list(records[0].keys())
        # Remove fiscal_quarter for annual statements, and date
        columns = [col for col in columns if col not in ['date'] and (period == "quarterly" or col != 'fiscal_quarter')]

        placeholders = ",".join(["%s"] * len(columns))
        column_list = ",".join(columns)

        values = []
        for record in records:
            row = tuple(record.get(col) for col in columns)
            values.append(row)

        sql = f"""
            INSERT INTO {table_name} ({column_list})
            VALUES %s
            ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                {', '.join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
        """

        execute_values(cur, sql, values)
        conn.commit()
        return len(values)

    except Exception as e:
        conn.rollback()
        logging.error(f"Failed to insert cash flow: {str(e)[:200]}")
        return 0
    finally:
        cur.close()

def load_symbol_financials(symbol: str) -> bool:
    """Load all financial statements for a symbol"""
    logging.info(f"Loading financials for {symbol}...")

    conn = get_db_connection()

    try:
        # Load balance sheet
        bs_records = load_balance_sheet(symbol, "annual")
        if bs_records:
            inserted = insert_balance_sheet(conn, bs_records, "annual")
            logging.info(f"  Balance Sheet: {inserted} records")

        # Load income statement
        income_records = load_income_statement(symbol, "annual")
        if income_records:
            inserted = insert_income_statement(conn, income_records, "annual")
            logging.info(f"  Income Statement: {inserted} records")

        # Load cash flow
        cf_records = load_cash_flow(symbol, "annual")
        if cf_records:
            inserted = insert_cash_flow(conn, cf_records, "annual")
            logging.info(f"  Cash Flow: {inserted} records")

        return True

    except Exception as e:
        logging.error(f"Error loading {symbol}: {str(e)[:200]}")
        return False

    finally:
        conn.close()

def main():
    # Get list of symbols
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol LIMIT 100")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    logging.info(f"Loading complete financial statements for {len(symbols)} symbols...")
    logging.info("This may take several minutes...")

    total_loaded = 0
    total_failed = 0

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(load_symbol_financials, symbol): symbol for symbol in symbols}

        for future in as_completed(futures):
            symbol = futures[future]
            try:
                if future.result():
                    total_loaded += 1
                else:
                    total_failed += 1
            except Exception as e:
                logging.error(f"Worker error for {symbol}: {str(e)[:100]}")
                total_failed += 1

    logging.info(f"\nComplete! Loaded {total_loaded} symbols, {total_failed} failed")

if __name__ == "__main__":
    main()
