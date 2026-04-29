#!/usr/bin/env python3
# TRIGGER: 20260429_145100 - Batch 5: Quarterly cash flow loader - VERIFICATION RUN

import sys
import logging
import os
import time
import json
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
        return psycopg2.connect(
            host=db_config["host"],
            port=db_config["port"],
            user=db_config["user"],
            password=db_config["password"],
            dbname=db_config["dbname"],
            connect_timeout=10
        )
    except Exception as e:
        logging.error(f"DB connection failed: {e}")
        return None

def safe_float(value) -> Optional[float]:
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(',', '').replace('$', '').strip()
            if not value or value == '-':
                return None
        return float(value)
    except Exception:
        return None

def main():
    logging.info("Starting loadquarterlycashflow.py")
    conn = get_db_connection()
    if not conn:
        return False

    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                fiscal_year INT NOT NULL,
                fiscal_quarter INT NOT NULL,
                date DATE,
                operating_cash_flow DECIMAL(16,2),
                investing_cash_flow DECIMAL(16,2),
                financing_cash_flow DECIMAL(16,2),
                capital_expenditures DECIMAL(16,2),
                free_cash_flow DECIMAL(16,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, fiscal_year, fiscal_quarter)
            )
        """)

        cur.execute("""
            SELECT DISTINCT ss.symbol FROM stock_symbols ss
            WHERE NOT EXISTS (
                SELECT 1 FROM quarterly_cash_flow t WHERE t.symbol = ss.symbol
            )
            ORDER BY ss.symbol
        """)
        symbols = [row[0] for row in cur.fetchall()]

        logging.info(f"Loading quarterly cash flows for {len(symbols)} stocks...")
        total_rows = 0

        for i, symbol in enumerate(symbols):
            try:
                time.sleep(REQUEST_DELAY)
                yf_symbol = symbol.replace(".", "-").upper()
                ticker = yf.Ticker(yf_symbol)
                try:
                    cf = ticker.quarterly_cashflow
                    if cf is None or cf.empty:
                        continue
                except Exception:
                    continue

                for date_col in cf.columns:
                    try:
                        fiscal_date = pd.to_datetime(date_col)
                        fiscal_year = fiscal_date.year
                        fiscal_quarter = (fiscal_date.month - 1) // 3 + 1
                        row_data = cf[date_col]

                        operating = safe_float(row_data.get('Operating Cash Flow'))
                        if operating is None:
                            continue

                        cur.execute("""
                            INSERT INTO quarterly_cash_flow
                            (symbol, fiscal_year, fiscal_quarter, operating_cash_flow,
                             investing_cash_flow, financing_cash_flow, capital_expenditures,
                             free_cash_flow, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (symbol, fiscal_year, fiscal_quarter) DO UPDATE SET
                            operating_cash_flow = EXCLUDED.operating_cash_flow,
                            investing_cash_flow = EXCLUDED.investing_cash_flow,
                            financing_cash_flow = EXCLUDED.financing_cash_flow,
                            capital_expenditures = EXCLUDED.capital_expenditures,
                            free_cash_flow = EXCLUDED.free_cash_flow,
                            updated_at = NOW()
                        """, (symbol, fiscal_year, fiscal_quarter,
                              operating,
                              safe_float(row_data.get('Investing Cash Flow')),
                              safe_float(row_data.get('Financing Cash Flow')),
                              safe_float(row_data.get('Capital Expenditure')),
                              safe_float(row_data.get('Free Cash Flow'))))
                        total_rows += 1
                    except Exception:
                        continue
            except Exception:
                continue
            if (i + 1) % 10 == 0:
                conn.commit()

        conn.commit()
        logging.info(f"Completed: {total_rows} rows")
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
