#!/usr/bin/env python3
# Triggered: 2026-04-28 14:55 UTC - Batch 5 Final Data
"""
Annual Cash Flow Loader
Loads annual cash flow statement data for all stocks from yfinance
"""

import sys
import logging
import os
import time
import json
from datetime import date
from typing import Optional

import psycopg2
import yfinance as yf
import pandas as pd
import requests
import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", stream=sys.stdout)

REQUEST_DELAY = 0.5

def get_db_connection():
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
            logging.info(f"Using AWS Secrets Manager for database config")
            db_config = {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables
    if not db_config:
        logging.info("Using environment variables for database config")
        db_config = {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

    try:
        conn = psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            dbname=db_config["dbname"],
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

def load_cash_flow_for_symbol(cur, symbol: str, attempt: int = 0) -> int:
    try:
        yf_symbol = symbol.replace(".", "-").upper()

        time.sleep(REQUEST_DELAY)

        ticker = yf.Ticker(yf_symbol)

        try:
            cash_flow = ticker.cashflow
            if cash_flow is None or cash_flow.empty:
                return 0
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < 3:
                wait_time = (2 ** attempt) * 5
                logging.warning(f"{symbol}: Rate limited, waiting {wait_time}s...")
                time.sleep(wait_time)
                return load_cash_flow_for_symbol(cur, symbol, attempt + 1)
            return 0
        except Exception:
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
                    (symbol, fiscal_year, operating_cash_flow, investing_cash_flow,
                     financing_cash_flow, capital_expenditures, free_cash_flow, dividends_paid, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (symbol, fiscal_year) DO UPDATE SET
                    operating_cash_flow = EXCLUDED.operating_cash_flow,
                    investing_cash_flow = EXCLUDED.investing_cash_flow,
                    financing_cash_flow = EXCLUDED.financing_cash_flow,
                    capital_expenditures = EXCLUDED.capital_expenditures,
                    free_cash_flow = EXCLUDED.free_cash_flow,
                    dividends_paid = EXCLUDED.dividends_paid,
                    updated_at = NOW()
                """, (symbol, fiscal_year,
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

        cur.execute("""
            SELECT DISTINCT ss.symbol FROM stock_symbols ss
            WHERE NOT EXISTS (
                SELECT 1 FROM annual_cash_flow t WHERE t.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)
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
        logging.info(f"Completed: {total_rows} rows inserted, {successful} successful")
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
