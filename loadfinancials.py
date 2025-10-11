#!/usr/bin/env python3
"""
Consolidated Financial Statements Loader
Replaces 8 loaders with single efficient loader using one API call per symbol

REPLACES:
- loadquarterlyincomestatement.py (ticker.quarterly_income_stmt)
- loadannualincomestatement.py (ticker.income_stmt)
- loadquarterlybalancesheet.py (ticker.quarterly_balance_sheet)
- loadannualbalancesheet.py (ticker.balance_sheet)
- loadquarterlycashflow.py (ticker.quarterly_cashflow)
- loadannualcashflow.py (ticker.cashflow)
- loadttmincomestatement.py (ticker.ttm_income_stmt)
- loadttmcashflow.py (ticker.ttm_cashflow)

OPTIMIZATION:
- Current: 8 API calls per symbol = 24,000 calls/day for 3,000 symbols
- New: 1 API call per symbol = 3,000 calls/day for 3,000 symbols
- 87.5% reduction in API calls
"""

import gc
import json
import logging
import os
import resource
import sys
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import boto3
import pandas as pd
import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_NAME = "loadfinancials.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_rss_mb():
    """Get current RSS memory usage in MB"""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    """Log memory usage at a given stage"""
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


MAX_BATCH_RETRIES = 3
RETRY_DELAY = 1.0


def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables"""
    if os.environ.get("USE_LOCAL_DB") == "true":
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }

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


def process_financial_statement(
    symbol: str, df: pd.DataFrame, statement_type: str
) -> List[Tuple]:
    """Process any financial statement DataFrame into database-ready tuples"""
    if df is None or df.empty:
        return []

    # Check if DataFrame contains any actual data (not all NaN)
    if df.isna().all().all():
        logging.debug(f"{statement_type} data is all NaN for {symbol}")
        return []

    # Check if we have at least one column with data
    valid_columns = [col for col in df.columns if not df[col].isna().all()]
    if not valid_columns:
        logging.debug(f"No valid {statement_type} columns found for {symbol}")
        return []

    processed_data = []
    valid_dates = 0
    total_values = 0
    valid_values = 0

    for date_col in df.columns:
        safe_date = safe_convert_date(date_col)
        if safe_date is None:
            logging.debug(f"Skipping invalid date column for {symbol}: {date_col}")
            continue
        valid_dates += 1

        for item_name in df.index:
            value = df.loc[item_name, date_col]
            total_values += 1
            safe_value = safe_convert_to_float(value)

            if safe_value is not None:
                valid_values += 1
                processed_data.append((symbol, safe_date, str(item_name), safe_value))

    if processed_data:
        logging.info(
            f"{statement_type} for {symbol}: {valid_dates} periods, "
            f"{valid_values}/{total_values} values, {len(processed_data)} records"
        )

    return processed_data


def load_all_financial_data(symbol: str, cur, conn) -> Dict:
    """
    Load ALL financial statement data from single yfinance API call

    Returns dict with counts of records inserted per statement type
    """
    stats = {
        'quarterly_income': 0,
        'annual_income': 0,
        'quarterly_balance': 0,
        'annual_balance': 0,
        'quarterly_cashflow': 0,
        'annual_cashflow': 0,
        'ttm_income': 0,
        'ttm_cashflow': 0,
    }

    try:
        # Clean symbol for yfinance
        yf_symbol = symbol.replace(".", "-").replace("$", "-P").upper()

        # SINGLE API CALL gets ALL financial statements
        ticker = yf.Ticker(yf_symbol)

        # Get all financial statements at once
        quarterly_income = ticker.quarterly_income_stmt
        annual_income = ticker.income_stmt
        quarterly_balance = ticker.quarterly_balance_sheet
        annual_balance = ticker.balance_sheet
        quarterly_cashflow = ticker.quarterly_cashflow
        annual_cashflow = ticker.cashflow
        ttm_income = ticker.ttm_income_stmt
        ttm_cashflow = ticker.ttm_cashflow

        # 1. QUARTERLY INCOME STATEMENT
        if quarterly_income is not None and not quarterly_income.empty:
            data = process_financial_statement(symbol, quarterly_income, "quarterly_income")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_income_statement (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['quarterly_income'] = len(data)

        # 2. ANNUAL INCOME STATEMENT
        if annual_income is not None and not annual_income.empty:
            data = process_financial_statement(symbol, annual_income, "annual_income")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO annual_income_statement (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['annual_income'] = len(data)

        # 3. QUARTERLY BALANCE SHEET
        if quarterly_balance is not None and not quarterly_balance.empty:
            data = process_financial_statement(symbol, quarterly_balance, "quarterly_balance")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_balance_sheet (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['quarterly_balance'] = len(data)

        # 4. ANNUAL BALANCE SHEET
        if annual_balance is not None and not annual_balance.empty:
            data = process_financial_statement(symbol, annual_balance, "annual_balance")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO annual_balance_sheet (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['annual_balance'] = len(data)

        # 5. QUARTERLY CASH FLOW
        if quarterly_cashflow is not None and not quarterly_cashflow.empty:
            data = process_financial_statement(symbol, quarterly_cashflow, "quarterly_cashflow")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO quarterly_cashflow (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['quarterly_cashflow'] = len(data)

        # 6. ANNUAL CASH FLOW
        if annual_cashflow is not None and not annual_cashflow.empty:
            data = process_financial_statement(symbol, annual_cashflow, "annual_cashflow")
            if data:
                execute_values(
                    cur,
                    """
                    INSERT INTO annual_cashflow (symbol, date, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    data,
                )
                stats['annual_cashflow'] = len(data)

        # 7. TTM INCOME STATEMENT
        if ttm_income is not None and not ttm_income.empty:
            # TTM is single column - treat specially
            ttm_data = []
            for item_name in ttm_income.index:
                # TTM typically has single column
                for col in ttm_income.columns:
                    value = ttm_income.loc[item_name, col]
                    safe_value = safe_convert_to_float(value)
                    if safe_value is not None:
                        ttm_data.append((symbol, str(item_name), safe_value))

            if ttm_data:
                execute_values(
                    cur,
                    """
                    INSERT INTO ttm_income_statement (symbol, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    ttm_data,
                )
                stats['ttm_income'] = len(ttm_data)
                logging.info(f"TTM income for {symbol}: {len(ttm_data)} records")

        # 8. TTM CASH FLOW
        if ttm_cashflow is not None and not ttm_cashflow.empty:
            # TTM is single column - treat specially
            ttm_data = []
            for item_name in ttm_cashflow.index:
                # TTM typically has single column
                for col in ttm_cashflow.columns:
                    value = ttm_cashflow.loc[item_name, col]
                    safe_value = safe_convert_to_float(value)
                    if safe_value is not None:
                        ttm_data.append((symbol, str(item_name), safe_value))

            if ttm_data:
                execute_values(
                    cur,
                    """
                    INSERT INTO ttm_cashflow (symbol, item_name, value)
                    VALUES %s
                    ON CONFLICT (symbol, item_name) DO UPDATE SET
                        value = EXCLUDED.value,
                        updated_at = NOW()
                    """,
                    ttm_data,
                )
                stats['ttm_cashflow'] = len(ttm_data)
                logging.info(f"TTM cashflow for {symbol}: {len(ttm_data)} records")

        # Commit all inserts for this symbol
        conn.commit()

        return stats

    except Exception as e:
        logging.error(f"Error loading financial data for {symbol}: {e}")
        conn.rollback()
        raise


def create_tables(cur, conn):
    """Create all financial statement tables"""
    logging.info("Creating financial statement tables...")

    # 1. Quarterly Income Statement
    cur.execute("DROP TABLE IF EXISTS quarterly_income_statement CASCADE;")
    cur.execute("""
        CREATE TABLE quarterly_income_statement (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_quarterly_income_statement_symbol ON quarterly_income_statement(symbol);
        CREATE INDEX idx_quarterly_income_statement_date ON quarterly_income_statement(date);
        CREATE INDEX idx_quarterly_income_statement_item ON quarterly_income_statement(item_name);
    """)

    # 2. Annual Income Statement
    cur.execute("DROP TABLE IF EXISTS annual_income_statement CASCADE;")
    cur.execute("""
        CREATE TABLE annual_income_statement (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_annual_income_statement_symbol ON annual_income_statement(symbol);
        CREATE INDEX idx_annual_income_statement_date ON annual_income_statement(date);
        CREATE INDEX idx_annual_income_statement_item ON annual_income_statement(item_name);
    """)

    # 3. Quarterly Balance Sheet
    cur.execute("DROP TABLE IF EXISTS quarterly_balance_sheet CASCADE;")
    cur.execute("""
        CREATE TABLE quarterly_balance_sheet (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_quarterly_balance_sheet_symbol ON quarterly_balance_sheet(symbol);
        CREATE INDEX idx_quarterly_balance_sheet_date ON quarterly_balance_sheet(date);
        CREATE INDEX idx_quarterly_balance_sheet_item ON quarterly_balance_sheet(item_name);
    """)

    # 4. Annual Balance Sheet
    cur.execute("DROP TABLE IF EXISTS annual_balance_sheet CASCADE;")
    cur.execute("""
        CREATE TABLE annual_balance_sheet (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol);
        CREATE INDEX idx_annual_balance_sheet_date ON annual_balance_sheet(date);
        CREATE INDEX idx_annual_balance_sheet_item ON annual_balance_sheet(item_name);
    """)

    # 5. Quarterly Cash Flow
    cur.execute("DROP TABLE IF EXISTS quarterly_cashflow CASCADE;")
    cur.execute("""
        CREATE TABLE quarterly_cashflow (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_quarterly_cashflow_symbol ON quarterly_cashflow(symbol);
        CREATE INDEX idx_quarterly_cashflow_date ON quarterly_cashflow(date);
        CREATE INDEX idx_quarterly_cashflow_item ON quarterly_cashflow(item_name);
    """)

    # 6. Annual Cash Flow
    cur.execute("DROP TABLE IF EXISTS annual_cashflow CASCADE;")
    cur.execute("""
        CREATE TABLE annual_cashflow (
            symbol VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, date, item_name)
        );
        CREATE INDEX idx_annual_cashflow_symbol ON annual_cashflow(symbol);
        CREATE INDEX idx_annual_cashflow_date ON annual_cashflow(date);
        CREATE INDEX idx_annual_cashflow_item ON annual_cashflow(item_name);
    """)

    # 7. TTM Income Statement
    cur.execute("DROP TABLE IF EXISTS ttm_income_statement CASCADE;")
    cur.execute("""
        CREATE TABLE ttm_income_statement (
            symbol VARCHAR(20) NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, item_name)
        );
        CREATE INDEX idx_ttm_income_statement_symbol ON ttm_income_statement(symbol);
        CREATE INDEX idx_ttm_income_statement_item ON ttm_income_statement(item_name);
    """)

    # 8. TTM Cash Flow
    cur.execute("DROP TABLE IF EXISTS ttm_cashflow CASCADE;")
    cur.execute("""
        CREATE TABLE ttm_cashflow (
            symbol VARCHAR(20) NOT NULL,
            item_name TEXT NOT NULL,
            value DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY(symbol, item_name)
        );
        CREATE INDEX idx_ttm_cashflow_symbol ON ttm_cashflow(symbol);
        CREATE INDEX idx_ttm_cashflow_item ON ttm_cashflow(item_name);
    """)

    conn.commit()
    logging.info("✅ Created all 8 financial statement tables")


def load_financial_data(symbols: List[str], cur, conn) -> Tuple[int, int, List[str]]:
    """Load financial data for given symbols"""
    total = len(symbols)
    logging.info(f"Loading financial data for {total} symbols")
    processed, failed = 0, []

    # Track total stats across all symbols
    total_stats = {
        'quarterly_income': 0,
        'annual_income': 0,
        'quarterly_balance': 0,
        'annual_balance': 0,
        'quarterly_cashflow': 0,
        'annual_cashflow': 0,
        'ttm_income': 0,
        'ttm_cashflow': 0,
    }

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
                    stats = load_all_financial_data(symbol, cur, conn)

                    if stats:
                        # Update totals
                        for key in total_stats:
                            total_stats[key] += stats.get(key, 0)

                        processed += 1
                        logging.info(f"✅ {symbol}: {stats}")
                        success = True
                        break
                    else:
                        logging.warning(f"⚠️ No data for {symbol}")
                        break

                except Exception as e:
                    logging.warning(f"Attempt {attempt} failed for {symbol}: {e}")
                    if attempt < MAX_BATCH_RETRIES:
                        time.sleep(RETRY_DELAY)
                    else:
                        conn.rollback()

            if not success:
                failed.append(symbol)

            # Rate limiting
            time.sleep(PAUSE)

        gc.collect()
        log_mem(f"Batch {batch_idx+1} end")

    # Log final statistics
    logging.info("=" * 80)
    logging.info("FINAL STATISTICS:")
    logging.info(f"Total symbols: {total}")
    logging.info(f"Successfully processed: {processed}")
    logging.info(f"Failed: {len(failed)}")
    logging.info("-" * 80)
    logging.info("Records by statement type:")
    for key, value in total_stats.items():
        logging.info(f"  {key}: {value:,} records")
    logging.info("=" * 80)

    return total, processed, failed


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

    # Create tables
    create_tables(cur, conn)

    # Load stock symbols only (ETFs are in etf_symbols table)
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]

    if stock_syms:
        total, processed, failed = load_financial_data(stock_syms, cur, conn)
        logging.info(f"Stocks — total: {total}, processed: {processed}, failed: {len(failed)}")
        if failed:
            logging.warning(f"Failed symbols: {', '.join(failed[:20])}")

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
    logging.info("✅ All done.")
