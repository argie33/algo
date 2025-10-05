#!/usr/bin/env python3
# Trigger rebuild: 20251005_061658
"""
Analyst Upgrade/Downgrade Data Loader
Updated: 2025-10-04 14:15 - Deploy analyst rating changes loader

This script fetches and loads analyst rating changes (upgrades, downgrades, initiations)
from Yahoo Finance into the PostgreSQL database. Analyst ratings are a key indicator
of professional sentiment and can influence stock prices significantly.

Key Features:
- Fetches analyst recommendation changes from Yahoo Finance (via yfinance)
- Captures firm name, action type, grade changes, and dates
- Drops and recreates table on each run for fresh data
- Batch inserts for performance
- Memory usage tracking and error handling
- Updates last_updated table for monitoring

Data Source:
- Yahoo Finance Ticker.recommendations property
- Includes historical rating changes from major analyst firms

Database Schema:
- analyst_upgrade_downgrade: Stores rating changes (symbol, firm, action, grades, date)
- last_updated: Tracks script execution timestamps

Rating Actions Include:
- Upgrades: Analyst raises rating (e.g., Hold → Buy)
- Downgrades: Analyst lowers rating (e.g., Buy → Hold)
- Initiations: Analyst begins coverage with initial rating
- Reiterations: Analyst confirms existing rating

Updated: 2025-10-03 22:45 - Trigger deployment to populate analyst upgrades/downgrades
"""
import gc
import json
import logging
import math
import os
import resource
import sys
import time
from datetime import datetime

import boto3
import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

SCRIPT_NAME = "loadanalystupgradedowngrade.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_rss_mb():
    """
    Get current memory usage in megabytes (RSS - Resident Set Size).

    Returns:
        float: Memory usage in MB. On Linux, converts from KB to MB.
               On other platforms (macOS), converts from bytes to MB.
    """
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024  # Linux reports in KB
    return usage / (1024 * 1024)  # macOS reports in bytes


def log_mem(stage: str):
    """
    Log current memory usage at a specific stage of execution.

    Args:
        stage: Descriptive label for the current execution stage
    """
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def get_db_config():
    """
    Retrieve database credentials from AWS Secrets Manager.

    Returns:
        dict: Database connection parameters including host, port, user,
              password, and dbname. Reads from DB_SECRET_ARN environment variable.

    Raises:
        KeyError: If DB_SECRET_ARN environment variable is not set
        ClientError: If secret retrieval from AWS Secrets Manager fails
    """
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


def create_table(cur):
    """
    Create (or recreate) the analyst_upgrade_downgrade table.

    This function drops the existing table and creates a fresh one to ensure
    clean data on each run. The table stores analyst rating changes including
    the firm making the change, the action type, and grade changes.

    Table Schema:
        - id: Auto-incrementing primary key
        - symbol: Stock ticker symbol (e.g., "AAPL")
        - firm: Name of analyst firm (e.g., "Morgan Stanley", "Goldman Sachs")
        - action: Type of action (e.g., "up", "down", "init", "main")
        - from_grade: Previous rating (e.g., "Hold", "Neutral")
        - to_grade: New rating (e.g., "Buy", "Overweight")
        - date: Date of the rating change
        - details: Additional context or comments from the analyst
        - fetched_at: Timestamp when data was loaded into database

    Args:
        cur: PostgreSQL cursor object

    Note:
        This uses DROP TABLE IF EXISTS, so existing data is lost on each run.
        This ensures fresh, up-to-date analyst ratings without duplicates.
    """
    logging.info("Recreating analyst_upgrade_downgrade table…")
    cur.execute("DROP TABLE IF EXISTS analyst_upgrade_downgrade;")
    cur.execute(
        """
        CREATE TABLE analyst_upgrade_downgrade (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(20) NOT NULL,
            firm         VARCHAR(128),
            action       VARCHAR(32),
            from_grade   VARCHAR(64),
            to_grade     VARCHAR(64),
            date         DATE NOT NULL,
            details      TEXT,
            fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )


def fetch_analyst_actions(symbol):
    """
    Fetch analyst recommendation changes for a given stock symbol.

    Uses the yfinance library to retrieve historical analyst rating changes
    from Yahoo Finance. The data includes upgrades, downgrades, initiations,
    and reiterations from various analyst firms.

    Data Fields from Yahoo Finance:
        - Firm: Name of the analyst firm
        - To Grade: New rating assigned
        - From Grade: Previous rating (if applicable)
        - Action: Type of change (e.g., "up", "down", "init", "main")
        - Details: Additional commentary from the analyst

    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "MSFT")

    Returns:
        pandas.DataFrame or None: DataFrame with analyst recommendations, or None
            if no data available or an error occurred. Only includes rows where
            either To Grade or From Grade is present (filters out empty entries).

    Note:
        Yahoo Finance provides this data through the ticker.recommendations property,
        not through get_analyst_price_target_history() which is not available.
    """
    # yfinance: Ticker(symbol).get_analyst_price_target_history() is not available, but recommendations is
    ticker = yf.Ticker(symbol)
    try:
        df = ticker.recommendations
    except Exception as e:
        logging.warning(f"Failed to fetch recommendations for {symbol}: {e}")
        return None
    if df is None or df.empty:
        return None
    # Only keep upgrade/downgrade actions (filter out rows with no grade information)
    df = df[df["To Grade"].notna() | df["From Grade"].notna()]
    return df


def load_analyst_actions(symbols, cur, conn):
    """
    Load analyst rating changes for a list of stock symbols into the database.

    This function orchestrates the data loading process:
    1. Iterates through each symbol
    2. Fetches analyst recommendations from Yahoo Finance
    3. Transforms the data into database-ready format
    4. Batch inserts the data using execute_values for performance
    5. Handles errors gracefully with rollback on failure
    6. Tracks memory usage and progress

    Data Transformation:
        - Extracts firm, action, grade changes, date, and details
        - Converts pandas DataFrame index (datetime) to date format
        - Handles missing fields gracefully with .get()

    Performance Optimizations:
        - Batch inserts using execute_values (much faster than individual INSERTs)
        - Manual garbage collection after each symbol to control memory
        - 50ms sleep between symbols to avoid overwhelming Yahoo Finance API
        - Commits after each symbol (not after all symbols) for crash resilience

    Args:
        symbols: List of stock ticker symbols to process
        cur: PostgreSQL cursor object
        conn: PostgreSQL connection object

    Returns:
        tuple: (total_symbols, total_inserted_rows, failed_symbols_list)
            - total_symbols (int): Number of symbols processed
            - total_inserted_rows (int): Number of rating changes inserted
            - failed_symbols_list (list): Symbols that failed to insert

    Error Handling:
        - Logs warnings for fetch failures but continues processing
        - Rolls back transaction on insert failure
        - Tracks failed symbols for reporting
    """
    total = len(symbols)
    logging.info(f"Loading analyst upgrades/downgrades: {total} symbols")
    inserted, failed = 0, []

    for idx, symbol in enumerate(symbols):
        # Log memory usage for each symbol to track resource consumption
        log_mem(f"{symbol} ({idx+1}/{total})")

        # Fetch analyst recommendations for this symbol
        df = fetch_analyst_actions(symbol)
        if df is None or df.empty:
            logging.info(f"No analyst upgrades/downgrades for {symbol}")
            continue

        # Transform DataFrame into list of tuples for batch insert
        rows = []
        for dt, row in df.iterrows():
            rows.append(
                [
                    symbol,
                    row.get("Firm"),  # Analyst firm name
                    row.get("Action"),  # Action type (up/down/init/main)
                    row.get("From Grade"),  # Previous rating
                    row.get("To Grade"),  # New rating
                    dt.date() if hasattr(dt, "date") else dt,  # Date of change
                    row.get("Details") if "Details" in row else None,  # Additional commentary
                ]
            )

        if not rows:
            continue

        # Batch insert using execute_values for performance
        sql = """
            INSERT INTO analyst_upgrade_downgrade
            (symbol, firm, action, from_grade, to_grade, date, details)
            VALUES %s
        """
        try:
            execute_values(cur, sql, rows)
            conn.commit()  # Commit after each symbol for crash resilience
            inserted += len(rows)
            logging.info(f"{symbol}: batch-inserted {len(rows)} rows")
        except Exception as e:
            logging.error(f"Failed to insert for {symbol}: {e}")
            conn.rollback()  # Rollback failed transaction
            failed.append(symbol)

        # Manual garbage collection to control memory usage
        gc.collect()
        # Small delay to avoid overwhelming Yahoo Finance API
        time.sleep(0.05)

    return total, inserted, failed


def lambda_handler(event, context):
    """
    Main execution function for the analyst upgrade/downgrade loader.

    This is the entry point when run as an AWS Lambda function. It can also
    be called directly when running the script standalone.

    Workflow:
    1. Establishes database connection using AWS Secrets Manager credentials
    2. Recreates analyst_upgrade_downgrade table (drops and recreates for fresh data)
    3. Queries stock_symbols table for all non-ETF symbols
    4. Fetches and loads analyst rating changes for each symbol
    5. Records execution timestamp in last_updated table
    6. Reports memory usage and execution statistics

    Database Tables Created/Modified:
        - analyst_upgrade_downgrade: Stores analyst rating changes
        - last_updated: Tracks when this script last ran

    Args:
        event: AWS Lambda event object (unused, for Lambda compatibility)
        context: AWS Lambda context object (unused, for Lambda compatibility)

    Returns:
        dict: Execution summary containing:
            - total (int): Number of symbols processed
            - inserted (int): Number of rating changes inserted
            - failed (list): Symbols that failed to load
            - peak_rss_mb (float): Peak memory usage in MB

    Note:
        This script uses DROP TABLE IF EXISTS to ensure a clean slate on each run.
        All existing analyst rating data is replaced with fresh data from Yahoo Finance.
        ETF symbols are excluded to focus on individual stocks only.
    """
    log_mem("startup")

    # Step 1: Connect to database using AWS Secrets Manager credentials
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False  # Use explicit transactions for better error handling
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Step 2: Recreate table for fresh data
    create_table(cur)
    conn.commit()

    # Step 3: Get list of all non-ETF stock symbols
    # ETFs are excluded because analyst ratings typically focus on individual stocks
    cur.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    stock_syms = [r["symbol"] for r in cur.fetchall()]

    # Step 4: Fetch and load analyst rating changes for all symbols
    t, i, f = load_analyst_actions(stock_syms, cur, conn)

    # Step 5: Record this script's execution timestamp for monitoring
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

    # Step 6: Report execution statistics
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(
        f"Analyst Upgrades/Downgrades — total: {t}, inserted: {i}, failed: {len(f)}"
    )

    # Clean up database connections
    cur.close()
    conn.close()
    logging.info("All done.")

    return {"total": t, "inserted": i, "failed": f, "peak_rss_mb": peak}
