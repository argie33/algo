#!/usr/bin/env python3
"""
Annual Cash Flow Loader
Loads annual cash flow statement data for all stocks from yfinance
"""

import sys
import logging
import os
from datetime import date
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
        logging.error(f"Failed to connect to database: {e}")
        return None

def safe_convert_to_float(value) -> Optional[float]:
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS annual_cash_flow (
            id SERIAL PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            fiscal_year INT NOT NULL,
            date DATE,
            operating_cash_flow DECIMAL(16,2),
            investing_cash_flow DECIMAL(16,2),
            financing_cash_flow DECIMAL(16,2),
            capital_expenditures DECIMAL(16,2),
            free_cash_flow DECIMAL(16,2),
            dividends_paid DECIMAL(16,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, fiscal_year)
        )
    """)

def load_cash_flow_for_symbol(cur, symbol: str) -> int:
    try:
        yf_symbol = symbol.replace(".", "-").upper()
        ticker = yf.Ticker(yf_symbol)

        try:
            cash_flow = ticker.cashflow
            if cash_flow is None or cash_flow.empty:
                return 0
        except:
            return 0

        rows_inserted = 0
        for date_col in cash_flow.columns:
            try:
                fiscal_date = pd.to_datetime(date_col)
                fiscal_year = fiscal_date.year
                row_data = cash_flow[date_col]

                operating = safe_convert_to_float(row_data.get('Operating Cash Flow'))
                investing = safe_convert_to_float(row_data.get('Investing Cash Flow'))
                financing = safe_convert_to_float(row_data.get('Financing Cash Flow'))
                capex = safe_convert_to_float(row_data.get('Capital Expenditure'))
                free_cf = safe_convert_to_float(row_data.get('Free Cash Flow'))
                dividends = safe_convert_to_float(row_data.get('Dividends Paid'))

                if operating is None:
                    continue

                cur.execute("""
                    INSERT INTO annual_cash_flow
                    (symbol, fiscal_year, date, operating_cash_flow, investing_cash_flow,
                     financing_cash_flow, capital_expenditures, free_cash_flow, dividends_paid, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                    operating_cash_flow = EXCLUDED.operating_cash_flow,
                    investing_cash_flow = EXCLUDED.investing_cash_flow,
                    financing_cash_flow = EXCLUDED.financing_cash_flow,
                    capital_expenditures = EXCLUDED.capital_expenditures,
                    free_cash_flow = EXCLUDED.free_cash_flow,
                    dividends_paid = EXCLUDED.dividends_paid,
                    updated_at = NOW()
                """, (symbol, fiscal_year, fiscal_date.date() if fiscal_date else None,
                      operating, investing, financing, capex, free_cf, dividends))
                rows_inserted += 1
            except Exception as e:
                logging.debug(f"Error processing row for {symbol}: {e}")
                continue
        return rows_inserted
    except Exception as e:
        logging.error(f"Error loading cash flow for {symbol}: {e}")
        return 0

def main():
    logging.info("Starting loadannualcashflow.py")
    conn = get_db_connection()
    if not conn:
        return False

    try:
        cur = conn.cursor()
        create_tables(cur)

        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Loading cash flows for {len(symbols)} stocks...")
        total_rows = 0
        successful = 0

        for i, symbol in enumerate(symbols):
            logging.info(f"[{i+1}/{len(symbols)}] Loading {symbol}...")
            rows = load_cash_flow_for_symbol(cur, symbol)
            total_rows += rows
            if rows > 0:
                successful += 1
            if (i + 1) % 10 == 0:
                conn.commit()

        conn.commit()
        logging.info(f"✓ Completed: {total_rows} rows inserted, {successful} successful")
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
