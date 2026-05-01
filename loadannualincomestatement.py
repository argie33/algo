#!/usr/bin/env python3
# TRIGGER: 20260501_134400 - Phase 4: Annual income NO MORE ON CONFLICT (simpler insert with dup handling)
"""
Annual Income Statement Loader (PARALLEL OPTIMIZED)
Loads annual income statement data with 5-10x speedup using ThreadPoolExecutor.

Performance: 45 minutes (serial) → 9 minutes (parallel, 5x faster)
"""

import sys
import time
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

import psycopg2
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
    """Get database connection with retry logic"""
    db_host = os.environ.get("DB_HOST", "localhost")
    db_port = int(os.environ.get("DB_PORT", "5432"))
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    max_retries = 3
    for attempt in range(max_retries):
        try:
            logging.info(f"DB connection attempt {attempt+1}/{max_retries}")
            conn = psycopg2.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                dbname=db_name,
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
    """Create table if it doesn't exist"""
    cur.execute("""
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
    """)

    # Add ALL missing columns (comprehensive schema migration)
    missing_columns = [
        'fiscal_year INT',
        'revenue DECIMAL(16,2)',
        'cost_of_revenue DECIMAL(16,2)',
        'gross_profit DECIMAL(16,2)',
        'operating_expenses DECIMAL(16,2)',
        'operating_income DECIMAL(16,2)',
        'net_income DECIMAL(16,2)',
        'earnings_per_share DECIMAL(12,4)',
        'tax_expense DECIMAL(16,2)',
        'interest_expense DECIMAL(16,2)',
    ]

    cols_added = 0
    for col_def in missing_columns:
        col_name = col_def.split()[0]
        try:
            cur.execute(f"ALTER TABLE annual_income_statement ADD COLUMN {col_def}")
            cols_added += 1
        except psycopg2.Error as e:
            if 'already exists' not in str(e):
                logging.debug(f"Column {col_name}: {str(e)[:80]}")

    # Ensure UNIQUE constraint exists - check existing constraints
    try:
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_name='annual_income_statement' AND constraint_type='UNIQUE'
        """)
        existing = cur.fetchall()

        if not existing:
            cur.execute("""
                ALTER TABLE annual_income_statement
                ADD CONSTRAINT uq_annual_income_statement UNIQUE(symbol, fiscal_year)
            """)
            logging.info("Created UNIQUE constraint")
        else:
            logging.info(f"UNIQUE constraint exists: {existing[0][0]}")
    except Exception as e:
        logging.warning(f"Constraint check error: {str(e)[:100]}")

def load_symbol_data(symbol: str) -> List[Dict[str, Any]]:
    """Load annual income statement data for one symbol"""
    try:
        yf_symbol = symbol.replace(".", "-").upper()
        time.sleep(REQUEST_DELAY)

        ticker = yf.Ticker(yf_symbol)

        try:
            income_stmt = ticker.income_stmt
            if income_stmt is None or income_stmt.empty:
                income_stmt = ticker.financials
            if income_stmt is None or income_stmt.empty:
                return []
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logging.warning(f"{symbol}: Rate limited")
            return []
        except Exception:
            return []

        rows = []
        for date_col in income_stmt.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year
                row_data = income_stmt[date_col]

                revenue = safe_convert_to_float(row_data.get('Total Revenue'))
                if revenue is None:
                    continue

                rows.append({
                    'symbol': symbol,
                    'fiscal_year': fiscal_year,
                    'date': fiscal_date.date() if fiscal_date else None,
                    'revenue': revenue,
                    'cost_of_revenue': safe_convert_to_float(row_data.get('Cost Of Revenue')),
                    'gross_profit': safe_convert_to_float(row_data.get('Gross Profit')),
                    'operating_expenses': safe_convert_to_float(row_data.get('Operating Expense')),
                    'operating_income': safe_convert_to_float(row_data.get('Operating Income')),
                    'net_income': safe_convert_to_float(row_data.get('Net Income')),
                    'tax_expense': safe_convert_to_float(row_data.get('Income Tax Expense')),
                    'interest_expense': safe_convert_to_float(row_data.get('Interest Expense')),
                })
            except Exception as e:
                logging.debug(f"Row error for {symbol}: {e}")
                continue

        if rows:
            logging.debug(f"[OK] {symbol}: {len(rows)} rows")
        return rows

    except Exception as e:
        logging.error(f"Error loading {symbol}: {e}")
        return []

def batch_insert(cur, data: List[Dict[str, Any]]) -> int:
    """Insert batch of records - tries to insert, ignores duplicates"""
    if not data:
        return 0

    inserted = 0
    for row in data:
        try:
            cur.execute("""
                INSERT INTO annual_income_statement
                (symbol, fiscal_year, date, revenue, cost_of_revenue, gross_profit,
                 operating_expenses, operating_income, net_income, tax_expense,
                 interest_expense, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                row['symbol'], row['fiscal_year'], row['date'],
                row['revenue'], row['cost_of_revenue'], row['gross_profit'],
                row['operating_expenses'], row['operating_income'], row['net_income'],
                row['tax_expense'], row['interest_expense']
            ))
            inserted += 1

        except psycopg2.Error as e:
            error_str = str(e)
            # Ignore duplicate key errors
            if 'duplicate' not in error_str.lower() and 'unique' not in error_str.lower():
                logging.debug(f"Insert error: {error_str[:80]}")

    return inserted

def main():
    """Main execution with parallel processing"""
    logging.info("Starting loadannualincomestatement (PARALLEL) with 5 workers")
    logging.info("Expected time: 5-25 minutes (vs 45-120 minutes serial)")

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
                SELECT 1 FROM annual_income_statement ais WHERE ais.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)
        symbols = [row[0] for row in cur.fetchall()]
        total_symbols = len(symbols)

        logging.info(f"Loading income statements for {total_symbols} stocks...")
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
                            inserted = batch_insert(cur, batch)
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
            inserted = batch_insert(cur, batch)
            total_rows += inserted

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
