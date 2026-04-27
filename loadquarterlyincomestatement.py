#!/usr/bin/env python3
"""
Quarterly Income Statement Loader
Loads quarterly income statement data from yfinance
"""

import sys
import logging
import os
from typing import Optional

import psycopg2
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

def get_db_connection():
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
        logging.error(f"Failed to connect: {e}")
        return None

def safe_convert_to_float(value) -> Optional[float]:
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
            if not value or value == '-':
                return None
        return float(value)
    except (ValueError, TypeError):
        return None

def create_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quarterly_income_statement (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            fiscal_quarter INT NOT NULL,
            date DATE,
            revenue DECIMAL(16,2),
            cost_of_revenue DECIMAL(16,2),
            gross_profit DECIMAL(16,2),
            operating_expenses DECIMAL(16,2),
            operating_income DECIMAL(16,2),
            net_income DECIMAL(16,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, fiscal_year, fiscal_quarter)
        )
    """)

def load_for_symbol(cur, symbol: str) -> int:
    try:
        yf_symbol = symbol.replace(".", "-").upper()
        ticker = yf.Ticker(yf_symbol)

        try:
            income_stmt = ticker.quarterly_income_stmt
            if income_stmt is None or income_stmt.empty:
                income_stmt = ticker.quarterly_financials
            if income_stmt is None or income_stmt.empty:
                return 0
        except Exception:
            return 0

        rows_inserted = 0
        for date_col in income_stmt.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year
                fiscal_quarter = (fiscal_date.month - 1) // 3 + 1
                row_data = income_stmt[date_col]

                revenue = safe_convert_to_float(row_data.get('Total Revenue'))
                if revenue is None:
                    continue

                cost_of_revenue = safe_convert_to_float(row_data.get('Cost Of Revenue'))
                gross_profit = safe_convert_to_float(row_data.get('Gross Profit'))
                operating_expenses = safe_convert_to_float(row_data.get('Operating Expense'))
                operating_income = safe_convert_to_float(row_data.get('Operating Income'))
                net_income = safe_convert_to_float(row_data.get('Net Income'))

                cur.execute("""
                    INSERT INTO quarterly_income_statement
                    (symbol, fiscal_year, fiscal_quarter, date, revenue, cost_of_revenue, gross_profit,
                     operating_expenses, operating_income, net_income, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
                    revenue = EXCLUDED.revenue,
                    cost_of_revenue = EXCLUDED.cost_of_revenue,
                    gross_profit = EXCLUDED.gross_profit,
                    operating_expenses = EXCLUDED.operating_expenses,
                    operating_income = EXCLUDED.operating_income,
                    net_income = EXCLUDED.net_income,
                    updated_at = NOW()
                """, (symbol, fiscal_year, fiscal_quarter, fiscal_date.date() if fiscal_date else None,
                      revenue, cost_of_revenue, gross_profit, operating_expenses, operating_income, net_income))
                rows_inserted += 1
            except Exception as e:
                logging.debug(f"Error for {symbol}: {e}")
                continue
        return rows_inserted
    except Exception as e:
        logging.error(f"Error for {symbol}: {e}")
        return 0

def main():
    logging.info("Starting loadquarterlyincomestatement.py")
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cur = conn.cursor()
        create_tables(cur)
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Loading quarterly income statements for {len(symbols)} stocks...")
        total_rows = 0

        for i, symbol in enumerate(symbols):
            rows = load_for_symbol(cur, symbol)
            total_rows += rows
            if (i + 1) % 10 == 0:
                conn.commit()

        conn.commit()
        logging.info(f"✓ Completed: {total_rows} rows inserted")
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
    sys.exit(0 if main() else 1)
