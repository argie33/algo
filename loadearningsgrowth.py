#!/usr/bin/env python3
"""
Earnings Growth Loader - Simplified focus on key growth metrics
Calculates quarter-over-quarter and year-over-year growth for EPS and revenue
"""
import concurrent.futures
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime

import boto3
import numpy as np
import pandas as pd
import psycopg2
from psycopg2 import pool
from psycopg2.extras import execute_values

# Script metadata
SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)

# Performance configuration
MAX_WORKERS = min(os.cpu_count() or 1, 4)
BATCH_SIZE = 100
DB_POOL_MIN = 2
DB_POOL_MAX = 10


def get_db_config():
    """Fetch database credentials from AWS Secrets Manager"""
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"],
    )


def safe_numeric(value):
    """Safely convert value to float, handling None, NaN, and invalid strings"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, str):
        value = value.strip()
        if value in ["", "N/A", "null", "NULL", "nan", "NaN"]:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def calculate_qoq_growth(current, previous):
    """Calculate quarter-over-quarter growth percentage"""
    current = safe_numeric(current)
    previous = safe_numeric(previous)

    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100


def calculate_yoy_growth(current, year_ago):
    """Calculate year-over-year growth percentage (same quarter last year)"""
    current = safe_numeric(current)
    year_ago = safe_numeric(year_ago)

    if current is None or year_ago is None or year_ago == 0:
        return None

    return ((current - year_ago) / abs(year_ago)) * 100


def prepare_db():
    """Setup database tables"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    conn.autocommit = True
    cursor = conn.cursor()
    logging.info("Connected to PostgreSQL database.")

    # Create last_updated table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name VARCHAR(255) PRIMARY KEY,
            last_run    TIMESTAMP
        );
        """
    )

    # Drop and recreate earnings_growth table
    logging.info("Recreating earnings_growth table...")
    cursor.execute("DROP TABLE IF EXISTS earnings_growth;")
    cursor.execute(
        """
        CREATE TABLE earnings_growth (
            symbol                  VARCHAR(50),
            report_date             DATE,
            eps_qoq_growth          DOUBLE PRECISION,  -- Quarter-over-quarter EPS growth %
            eps_yoy_growth          DOUBLE PRECISION,  -- Year-over-year EPS growth %
            revenue_yoy_growth      DOUBLE PRECISION,  -- Year-over-year Revenue growth %
            earnings_surprise_pct   DOUBLE PRECISION,  -- Earnings surprise %
            fetched_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (symbol, report_date)
        );
        """
    )
    logging.info("Table 'earnings_growth' ready.")

    # Get stock symbols (exclude ETFs)
    cursor.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"Found {len(symbols)} symbols.")

    cursor.close()
    conn.close()
    return symbols


def create_connection_pool():
    """Create database connection pool"""
    user, pwd, host, port, db = get_db_config()
    return pool.ThreadedConnectionPool(
        DB_POOL_MIN,
        DB_POOL_MAX,
        host=host,
        port=port,
        user=user,
        password=pwd,
        dbname=db,
    )


def process_symbol(symbol, conn_pool):
    """Process a single symbol and calculate growth metrics"""
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        logging.info(f"Processing earnings growth for {symbol}...")

        # Get earnings history (EPS data)
        cursor.execute(
            """
            SELECT quarter, eps_actual, eps_estimate, surprise_percent
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter DESC
            LIMIT 20
            """,
            (symbol,),
        )
        earnings_history = cursor.fetchall()

        if not earnings_history:
            logging.warning(f"No earnings history for {symbol}, skipping.")
            conn_pool.putconn(conn)
            return 0

        # Get revenue estimates for revenue growth
        cursor.execute(
            """
            SELECT period, avg_estimate, year_ago_revenue, growth
            FROM revenue_estimates
            WHERE symbol = %s
            ORDER BY period DESC
            LIMIT 8
            """,
            (symbol,),
        )
        revenue_estimates = cursor.fetchall()

        # Convert to DataFrame for easier processing
        earnings_df = pd.DataFrame(
            earnings_history,
            columns=["quarter", "eps_actual", "eps_estimate", "surprise_percent"],
        )
        earnings_df["quarter"] = pd.to_datetime(earnings_df["quarter"])

        # Convert numeric columns
        for col in ["eps_actual", "eps_estimate", "surprise_percent"]:
            earnings_df[col] = earnings_df[col].apply(safe_numeric)

        earnings_df = earnings_df.sort_values("quarter")

        # Calculate metrics for each quarter
        data = []
        for i in range(len(earnings_df)):
            row = earnings_df.iloc[i]
            report_date = row["quarter"]
            eps_actual = row["eps_actual"]
            surprise_pct = row["surprise_percent"]

            # Quarter-over-quarter growth (current vs previous quarter)
            eps_qoq_growth = None
            if i > 0:
                prev_eps = earnings_df.iloc[i - 1]["eps_actual"]
                eps_qoq_growth = calculate_qoq_growth(eps_actual, prev_eps)

            # Year-over-year growth (current vs same quarter last year)
            eps_yoy_growth = None
            if i >= 4:  # Need at least 4 quarters (1 year) of history
                year_ago_eps = earnings_df.iloc[i - 4]["eps_actual"]
                eps_yoy_growth = calculate_yoy_growth(eps_actual, year_ago_eps)

            # Revenue growth - get most recent available
            revenue_yoy_growth = None
            if revenue_estimates:
                for period, avg_est, year_ago_rev, growth in revenue_estimates:
                    growth_val = safe_numeric(growth)
                    if growth_val is not None:
                        revenue_yoy_growth = growth_val
                        break

            data.append(
                (
                    symbol,
                    report_date.date(),
                    eps_qoq_growth,
                    eps_yoy_growth,
                    revenue_yoy_growth,
                    surprise_pct,
                    datetime.now(),
                )
            )

        # Insert data
        if data:
            insert_q = """
                INSERT INTO earnings_growth (
                    symbol, report_date, eps_qoq_growth, eps_yoy_growth,
                    revenue_yoy_growth, earnings_surprise_pct, fetched_at
                ) VALUES %s;
            """
            execute_values(cursor, insert_q, data)
            conn.commit()
            num_inserted = len(data)
            logging.info(f"✅ {symbol}: Inserted {num_inserted} rows")
        else:
            num_inserted = 0
            logging.warning(f"⚠️ {symbol}: No data to insert")

        cursor.close()
        conn_pool.putconn(conn)

        # Free memory
        del earnings_df, earnings_history, revenue_estimates, data
        gc.collect()

        return num_inserted

    except Exception as e:
        logging.error(f"❌ {symbol}: Failed - {str(e)}")
        if "conn" in locals() and conn:
            conn_pool.putconn(conn)
        return 0


def process_symbol_batch(symbols):
    """Process a batch of symbols"""
    conn_pool = create_connection_pool()
    total_inserted = 0
    success_count = 0
    failed_count = 0

    try:
        for symbol in symbols:
            try:
                inserted = process_symbol(symbol, conn_pool)
                total_inserted += inserted
                if inserted > 0:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"❌ Batch error for {symbol}: {str(e)}")
                failed_count += 1
    finally:
        conn_pool.closeall()

    return total_inserted, success_count, failed_count


def main():
    logging.info(f"Starting {SCRIPT_NAME}")
    try:
        symbols = prepare_db()
        start = time.time()
        total_inserted = 0
        symbols_processed = 0
        symbols_failed = 0

        # Process symbols in parallel
        with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            symbol_batches = [
                symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)
            ]
            futures = [executor.submit(process_symbol_batch, batch) for batch in symbol_batches]

            for future in concurrent.futures.as_completed(futures):
                batch_inserted, batch_success, batch_failed = future.result()
                total_inserted += batch_inserted
                symbols_processed += batch_success
                symbols_failed += batch_failed

        elapsed = time.time() - start
        logging.info(
            f"Summary: Processed {symbols_processed + symbols_failed} symbols in {elapsed:.2f}s"
        )
        logging.info(f"Success: {symbols_processed} symbols ({total_inserted} rows)")
        if symbols_failed > 0:
            logging.warning(f"Failed: {symbols_failed} symbols")
        else:
            logging.info("✨ All symbols processed successfully")

        # Update last_run timestamp
        main_conn_pool = create_connection_pool()
        conn = main_conn_pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, %s)
            ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;
            """,
            (SCRIPT_NAME, datetime.now()),
        )
        conn.commit()
        cursor.close()
        main_conn_pool.putconn(conn)
        main_conn_pool.closeall()

    except Exception as e:
        logging.exception(f"Unhandled error: {e}")
        sys.exit(1)
    finally:
        logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled error in script")
        sys.exit(1)
