#!/usr/bin/env python3
"""
Flexible Financial Statement Loader - Loads ALL yfinance columns dynamically
"""

import os
import sys
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
import yfinance as yf

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def normalize_column_name(name: str) -> str:
    """Convert yfinance column name to valid SQL name"""
    return name.lower().replace(" ", "_").replace("/", "").replace("&", "and").replace("-", "_").replace("(", "").replace(")", "").replace(".", "").replace(",", "").replace("'", "")

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", 5432),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME", "stocks")
    )

def safe_int(val):
    """Safely convert value to int"""
    if val is None:
        return None
    try:
        return int(float(val))
    except:
        return None

def add_column_if_not_exists(conn, table_name: str, column_name: str):
    """Add column to table if it doesn't exist"""
    cur = conn.cursor()
    try:
        cur.execute(f"""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, (table_name, column_name))

        if not cur.fetchone():
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} BIGINT")
            conn.commit()
            return True
        return False
    except Exception as e:
        conn.rollback()
        return False
    finally:
        cur.close()

def load_and_insert_balance_sheet(conn, symbol: str):
    """Load and insert balance sheet for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        bs = ticker.balance_sheet

        if bs is None or len(bs) == 0 or len(bs.columns) == 0:
            return 0

        inserted = 0
        for date, row in bs.items():
            try:
                fiscal_year = date.year
                insert_dict = {"symbol": symbol, "fiscal_year": fiscal_year}

                for col_name in bs.index:
                    value = row.get(col_name)
                    if value is not None:
                        sql_col = normalize_column_name(col_name)
                        # Add column if needed
                        add_column_if_not_exists(conn, "annual_balance_sheet", sql_col)
                        insert_dict[sql_col] = safe_int(value)

                if len(insert_dict) > 2:  # More than just symbol and fiscal_year
                    columns = list(insert_dict.keys())
                    placeholders = ",".join(["%s"] * len(columns))
                    values = tuple(insert_dict[col] for col in columns)

                    cur = conn.cursor()
                    sql = f"""
                        INSERT INTO annual_balance_sheet ({",".join(columns)})
                        VALUES ({",".join(["%s"] * len(columns))})
                        ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                            {",".join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
                    """
                    cur.execute(sql, values)
                    conn.commit()
                    cur.close()
                    inserted += 1

            except Exception as e:
                conn.rollback()
                logging.warning(f"Failed to insert row for {symbol} {date}: {str(e)[:100]}")

        return inserted

    except Exception as e:
        logging.warning(f"Failed to load balance sheet for {symbol}: {str(e)[:100]}")
        return 0

def load_and_insert_income_statement(conn, symbol: str):
    """Load and insert income statement for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        income = ticker.income_stmt

        if income is None or len(income) == 0 or len(income.columns) == 0:
            return 0

        inserted = 0
        for date, row in income.items():
            try:
                fiscal_year = date.year
                insert_dict = {"symbol": symbol, "fiscal_year": fiscal_year}

                for col_name in income.index:
                    value = row.get(col_name)
                    if value is not None:
                        sql_col = normalize_column_name(col_name)
                        # Add column if needed
                        add_column_if_not_exists(conn, "annual_income_statement", sql_col)
                        insert_dict[sql_col] = safe_int(value)

                if len(insert_dict) > 2:  # More than just symbol and fiscal_year
                    columns = list(insert_dict.keys())
                    values = tuple(insert_dict[col] for col in columns)

                    cur = conn.cursor()
                    sql = f"""
                        INSERT INTO annual_income_statement ({",".join(columns)})
                        VALUES ({",".join(["%s"] * len(columns))})
                        ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                            {",".join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
                    """
                    cur.execute(sql, values)
                    conn.commit()
                    cur.close()
                    inserted += 1

            except Exception as e:
                conn.rollback()
                logging.warning(f"Failed to insert row for {symbol} {date}: {str(e)[:100]}")

        return inserted

    except Exception as e:
        logging.warning(f"Failed to load income statement for {symbol}: {str(e)[:100]}")
        return 0

def load_and_insert_cash_flow(conn, symbol: str):
    """Load and insert cash flow for a symbol"""
    try:
        ticker = yf.Ticker(symbol)
        cf = ticker.cashflow

        if cf is None or len(cf) == 0 or len(cf.columns) == 0:
            return 0

        inserted = 0
        for date, row in cf.items():
            try:
                fiscal_year = date.year
                insert_dict = {"symbol": symbol, "fiscal_year": fiscal_year}

                for col_name in cf.index:
                    value = row.get(col_name)
                    if value is not None:
                        sql_col = normalize_column_name(col_name)
                        # Add column if needed
                        add_column_if_not_exists(conn, "annual_cash_flow", sql_col)
                        insert_dict[sql_col] = safe_int(value)

                if len(insert_dict) > 2:  # More than just symbol and fiscal_year
                    columns = list(insert_dict.keys())
                    values = tuple(insert_dict[col] for col in columns)

                    cur = conn.cursor()
                    sql = f"""
                        INSERT INTO annual_cash_flow ({",".join(columns)})
                        VALUES ({",".join(["%s"] * len(columns))})
                        ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                            {",".join(f'{col} = EXCLUDED.{col}' for col in columns if col not in ['symbol', 'fiscal_year'])}
                    """
                    cur.execute(sql, values)
                    conn.commit()
                    cur.close()
                    inserted += 1

            except Exception as e:
                conn.rollback()
                logging.warning(f"Failed to insert row for {symbol} {date}: {str(e)[:100]}")

        return inserted

    except Exception as e:
        logging.warning(f"Failed to load cash flow for {symbol}: {str(e)[:100]}")
        return 0

def load_symbol_financials(symbol: str) -> bool:
    """Load all financials for a symbol"""
    logging.info(f"Loading {symbol}...")
    conn = get_db_connection()

    try:
        bs_count = load_and_insert_balance_sheet(conn, symbol)
        income_count = load_and_insert_income_statement(conn, symbol)
        cf_count = load_and_insert_cash_flow(conn, symbol)

        if bs_count > 0 or income_count > 0 or cf_count > 0:
            logging.info(f"  [+] {symbol}: BS={bs_count}, IS={income_count}, CF={cf_count}")
            return True
        else:
            logging.warning(f"  [-] {symbol}: No data loaded")
            return False

    except Exception as e:
        logging.error(f"Error with {symbol}: {str(e)[:100]}")
        return False

    finally:
        conn.close()

def main():
    # Get list of symbols
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol LIMIT 50")
    symbols = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()

    logging.info(f"Loading financials for {len(symbols)} symbols...")

    total_loaded = 0
    total_failed = 0

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(load_symbol_financials, symbol): symbol for symbol in symbols}

        for future in as_completed(futures):
            try:
                if future.result():
                    total_loaded += 1
                else:
                    total_failed += 1
            except Exception as e:
                logging.error(f"Worker error: {str(e)[:100]}")
                total_failed += 1

    logging.info(f"\nComplete! Loaded {total_loaded} symbols, {total_failed} failed")

if __name__ == "__main__":
    main()
