#!/usr/bin/env python3
# Updated: 2025-10-04 13:50 - Financial data loader
import gc
import json
import logging
import os
import resource
import sys
import time
from datetime import date, datetime
from typing import List, Optional, Tuple

import boto3
import pandas as pd
import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_NAME = "loadannualcashflow.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


MAX_BATCH_RETRIES = 3
RETRY_DELAY = 1.0


def get_db_config():
    secret_str = boto3.client("secretsmanager").get_secret_value(
        SecretId=os.environ["DB_SECRET_ARN"]
    )["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"],
    }


def safe_convert_to_float(value) -> Optional[float]:
    """Safely convert value to float, handling various edge cases"""
    if pd.isna(value) or value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.replace(",", "").replace("$", "").strip()
            if value == "" or value == "-" or value.lower() == "n/a":
                return None
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_convert_date(dt) -> Optional[date]:
    """Safely convert various date formats to date object"""
    if pd.isna(dt) or dt is None:
        return None
    try:
        if hasattr(dt, "date"):
            return dt.date()
        elif isinstance(dt, str):
            return datetime.strptime(dt, "%Y-%m-%d").date()
        elif isinstance(dt, date):
            return dt
        else:
            return pd.to_datetime(dt).date()
    except (ValueError, TypeError):
        return None


def get_cash_flow_data(symbol: str) -> Optional[pd.DataFrame]:
    """Get annual cash flow data using proper yfinance API with fallback methods"""
    try:
        ticker = yf.Ticker(symbol)

        # Try multiple methods in order of preference
        methods_to_try = [
            ("cash_flow", "annual cash flow (new method)"),
            ("cashflow", "annual cash flow (legacy method)"),
        ]

        cash_flow = None

        for method_name, description in methods_to_try:
            try:
                if hasattr(ticker, method_name):
                    logging.info(f"Trying {method_name} for {symbol}")
                    cash_flow = getattr(ticker, method_name)

                    if cash_flow is not None and not cash_flow.empty:
                        logging.info(
                            f"✓ Successfully got data using {method_name} for {symbol}"
                        )
                        break
                    else:
                        logging.warning(
                            f"{method_name} returned empty data for {symbol}"
                        )
                else:
                    logging.warning(f"Method {method_name} not available for {symbol}")
            except Exception as e:
                logging.warning(f"Error with {method_name} for {symbol}: {e}")
                continue

        if cash_flow is None or cash_flow.empty:
            logging.warning(f"No cash flow data returned by any method for {symbol}")
            return None

        # Check if DataFrame contains any actual data (not all NaN)
        if cash_flow.isna().all().all():
            logging.warning(f"Cash flow data is all NaN for {symbol}")
            return None

        # Check if we have at least one column with data
        valid_columns = [
            col for col in cash_flow.columns if not cash_flow[col].isna().all()
        ]
        if not valid_columns:
            logging.warning(f"No valid cash flow columns found for {symbol}")
            return None

        # Sort columns by date (most recent first)
        cash_flow = cash_flow.reindex(sorted(cash_flow.columns, reverse=True), axis=1)

        logging.info(
            f"Retrieved cash flow data for {symbol}: {len(cash_flow.columns)} periods, {len(cash_flow.index)} line items"
        )
        return cash_flow

    except Exception as e:
        logging.error(f"Error fetching cash flow for {symbol}: {e}")
        return None


def process_cash_flow_data(symbol: str, cash_flow: pd.DataFrame) -> List[Tuple]:
    """Process cash flow DataFrame into database-ready tuples"""
    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0

    for date_col in cash_flow.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1

        for item_name in cash_flow.index:
            value = cash_flow.loc[item_name, date_col]
            total_values += 1
            safe_value = safe_convert_to_float(value)

            if safe_value is not None:
                valid_values += 1
                processed_data.append((symbol, safe_date, str(item_name), safe_value))

    logging.info(
        f"Processed {symbol}: {valid_dates} valid dates, {valid_values}/{total_values} valid values, {len(processed_data)} records"
    )
    return processed_data


def load_annual_cash_flow(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load annual cash flow data for given symbols"""
    total = len(symbols)
    logging.info(f"Loading annual cash flow for {total} symbols")
    processed, failed = 0, []
    CHUNK_SIZE, PAUSE = 10, 0.5
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch = symbols[batch_idx * CHUNK_SIZE : (batch_idx + 1) * CHUNK_SIZE]
        logging.info(f"Processing batch {batch_idx+1}/{batches}")
        log_mem(f"Batch {batch_idx+1} start")

        for symbol in batch:
            success = False

            for attempt in range(1, MAX_BATCH_RETRIES + 1):
                try:
                    # Clean symbol for yfinance (handle special characters)
                    yf_symbol = symbol.replace(".", "-").replace("$", "-P").upper()

                    cash_flow = get_cash_flow_data(yf_symbol)
                    if cash_flow is None:
                        break

                    # Process the data
                    cash_flow_data = process_cash_flow_data(symbol, cash_flow)

                    if cash_flow_data:
                        # Insert data
                        execute_values(
                            cur,
                            """
                            INSERT INTO annual_cash_flow (symbol, date, item_name, value)
                            VALUES %s
                            ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                                value = EXCLUDED.value,
                                updated_at = NOW()
                        """,
                            cash_flow_data,
                        )
                        conn.commit()
                        processed += 1
                        logging.info(
                            f"✓ Successfully processed {symbol} ({len(cash_flow_data)} records)"
                        )
                        success = True
                        break
                    else:
                        logging.warning(
                            f"✗ No valid data found for {symbol} after processing"
                        )
                        break

                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {symbol}: {e}")
                    if attempt < MAX_BATCH_RETRIES:
                        time.sleep(RETRY_DELAY)
                    else:
                        conn.rollback()

            if not success:
                failed.append(symbol)

        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, processed, failed


def create_table(cur, conn):
    """Create the annual cash flow table"""
    logging.info("Creating annual cash flow table...")
    cur.execute("DROP TABLE IF EXISTS annual_cash_flow CASCADE;")

    create_table_sql = """
        CREATE TABLE annual_cash_flow (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        
        CREATE INDEX idx_annual_cash_flow_symbol ON annual_cash_flow(symbol);
        CREATE INDEX idx_annual_cash_flow_date ON annual_cash_flow(date);
        CREATE INDEX idx_annual_cash_flow_item ON annual_cash_flow(item_name);
    """
    cur.execute(create_table_sql)
    conn.commit()
    logging.info("Created annual cash flow table")


if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create table
    create_table(cur, conn)

    # Load stock symbols only (ETFs are in etf_symbols table and not processed by this loader)
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    if stock_syms:
        t_s, p_s, f_s = load_annual_cash_flow(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {t_s}, processed: {p_s}, failed: {len(f_s)}")

    # Record last run
    cur.execute(
        """
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
    """,
        (SCRIPT_NAME,),
    )
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")

    cur.close()
    conn.close()
    logging.info("All done.")
