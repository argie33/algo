#!/usr/bin/env python3
import sys
import time
import logging
import functools
import os
import json
import resource

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd
import math

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "WARNING"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True
)
logger = logging.getLogger(__name__)

# -------------------------------
# Environment-driven configuration
# -------------------------------
DB_SECRET_ARN = os.getenv("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN environment variable is not set")
    sys.exit(1)

def get_db_config():
    """
    Fetch host, port, dbname, username & password from Secrets Manager.
    SecretString must be JSON with keys: username, password, host, port, dbname.
    """
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return (
        sec["username"],
        sec["password"],
        sec["host"],
        int(sec["port"]),
        sec["dbname"]
    )

def get_rss_mb():
    """Get current RSS memory usage in MB"""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    """Log current memory usage with stage label"""
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

def retry(max_attempts=3, initial_delay=2, backoff=2):
    """Retry decorator with exponential backoff."""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, conn, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, conn, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{f.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}",
                        exc_info=True
                    )
                    if attempts < max_attempts:
                        time.sleep(delay)
                        delay *= backoff
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {f.__name__} with symbol {symbol}"
            )
        return wrapper
    return decorator

def clean_value(value):
    """Convert NaN or None to None, otherwise keep value"""
    if pd.isna(value) or value is None:
        return None
    if isinstance(value, (pd.Timestamp, pd.DatetimeTZDtype)):
        return value.to_pydatetime()
    return value

def ensure_tables(conn):
    """Create all required financial tables"""
    with conn.cursor() as cur:
        # Annual Balance Sheet
        cur.execute("DROP TABLE IF EXISTS balance_sheet_annual;")
        cur.execute("""
            CREATE TABLE balance_sheet_annual (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                short_term_investments DOUBLE PRECISION,
                net_receivables DOUBLE PRECISION,
                inventory      DOUBLE PRECISION,
                other_current_assets DOUBLE PRECISION,
                total_current_assets DOUBLE PRECISION,
                long_term_investments DOUBLE PRECISION,
                property_plant_equipment DOUBLE PRECISION,
                goodwill      DOUBLE PRECISION,
                intangible_assets DOUBLE PRECISION,
                other_assets  DOUBLE PRECISION,
                accounts_payable DOUBLE PRECISION,
                short_term_debt DOUBLE PRECISION,
                other_current_liab DOUBLE PRECISION,
                long_term_debt DOUBLE PRECISION,
                other_liab    DOUBLE PRECISION,
                retained_earnings DOUBLE PRECISION,
                total_stockholder_equity DOUBLE PRECISION,
                net_tangible_assets DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Quarterly Balance Sheet
        cur.execute("DROP TABLE IF EXISTS balance_sheet_quarterly;")
        cur.execute("""
            CREATE TABLE balance_sheet_quarterly (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                short_term_investments DOUBLE PRECISION,
                net_receivables DOUBLE PRECISION,
                inventory      DOUBLE PRECISION,
                other_current_assets DOUBLE PRECISION,
                total_current_assets DOUBLE PRECISION,
                long_term_investments DOUBLE PRECISION,
                property_plant_equipment DOUBLE PRECISION,
                goodwill      DOUBLE PRECISION,
                intangible_assets DOUBLE PRECISION,
                other_assets  DOUBLE PRECISION,
                accounts_payable DOUBLE PRECISION,
                short_term_debt DOUBLE PRECISION,
                other_current_liab DOUBLE PRECISION,
                long_term_debt DOUBLE PRECISION,
                other_liab    DOUBLE PRECISION,
                retained_earnings DOUBLE PRECISION,
                total_stockholder_equity DOUBLE PRECISION,
                net_tangible_assets DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Annual Income Statement
        cur.execute("DROP TABLE IF EXISTS income_statement_annual;")
        cur.execute("""
            CREATE TABLE income_statement_annual (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_revenue  DOUBLE PRECISION,
                cost_of_revenue DOUBLE PRECISION,
                gross_profit   DOUBLE PRECISION,
                research_development DOUBLE PRECISION,
                selling_general_admin DOUBLE PRECISION,
                operating_expenses DOUBLE PRECISION,
                operating_income DOUBLE PRECISION,
                interest_expense DOUBLE PRECISION,
                total_other_income DOUBLE PRECISION,
                income_before_tax DOUBLE PRECISION,
                income_tax_expense DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                ebitda       DOUBLE PRECISION,
                ebit         DOUBLE PRECISION,
                basic_eps     DOUBLE PRECISION,
                diluted_eps   DOUBLE PRECISION,
                shares_outstanding DOUBLE PRECISION,
                shares_diluted DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Quarterly Income Statement
        cur.execute("DROP TABLE IF EXISTS income_statement_quarterly;")
        cur.execute("""
            CREATE TABLE income_statement_quarterly (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_revenue  DOUBLE PRECISION,
                cost_of_revenue DOUBLE PRECISION,
                gross_profit   DOUBLE PRECISION,
                research_development DOUBLE PRECISION,
                selling_general_admin DOUBLE PRECISION,
                operating_expenses DOUBLE PRECISION,
                operating_income DOUBLE PRECISION,
                interest_expense DOUBLE PRECISION,
                total_other_income DOUBLE PRECISION,
                income_before_tax DOUBLE PRECISION,
                income_tax_expense DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                ebitda       DOUBLE PRECISION,
                ebit         DOUBLE PRECISION,
                basic_eps     DOUBLE PRECISION,
                diluted_eps   DOUBLE PRECISION,
                shares_outstanding DOUBLE PRECISION,
                shares_diluted DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Annual Cash Flow
        cur.execute("DROP TABLE IF EXISTS cash_flow_annual;")
        cur.execute("""
            CREATE TABLE cash_flow_annual (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                operating_cashflow DOUBLE PRECISION,
                capital_expenditure DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                depreciation  DOUBLE PRECISION,
                change_in_working_capital DOUBLE PRECISION,
                change_in_receivables DOUBLE PRECISION,
                change_in_inventory DOUBLE PRECISION,
                change_in_account_payables DOUBLE PRECISION,
                other_operating_cashflow DOUBLE PRECISION,
                investing_cashflow DOUBLE PRECISION,
                financing_cashflow DOUBLE PRECISION,
                dividend_paid DOUBLE PRECISION,
                stock_sale_repurchase DOUBLE PRECISION,
                net_borrowings DOUBLE PRECISION,
                other_financing_cashflow DOUBLE PRECISION,
                effect_of_forex_changes DOUBLE PRECISION,
                net_change_in_cash DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Quarterly Cash Flow
        cur.execute("DROP TABLE IF EXISTS cash_flow_quarterly;")
        cur.execute("""
            CREATE TABLE cash_flow_quarterly (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                operating_cashflow DOUBLE PRECISION,
                capital_expenditure DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                depreciation  DOUBLE PRECISION,
                change_in_working_capital DOUBLE PRECISION,
                change_in_receivables DOUBLE PRECISION,
                change_in_inventory DOUBLE PRECISION,
                change_in_account_payables DOUBLE PRECISION,
                other_operating_cashflow DOUBLE PRECISION,
                investing_cashflow DOUBLE PRECISION,
                financing_cashflow DOUBLE PRECISION,
                dividend_paid DOUBLE PRECISION,
                stock_sale_repurchase DOUBLE PRECISION,
                net_borrowings DOUBLE PRECISION,
                other_financing_cashflow DOUBLE PRECISION,
                effect_of_forex_changes DOUBLE PRECISION,
                net_change_in_cash DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)


        # TTM Balance Sheet
        cur.execute("DROP TABLE IF EXISTS balance_sheet_ttm;")
        cur.execute("""
            CREATE TABLE balance_sheet_ttm (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                short_term_investments DOUBLE PRECISION,
                net_receivables DOUBLE PRECISION,
                inventory      DOUBLE PRECISION,
                other_current_assets DOUBLE PRECISION,
                total_current_assets DOUBLE PRECISION,
                long_term_investments DOUBLE PRECISION,
                property_plant_equipment DOUBLE PRECISION,
                goodwill      DOUBLE PRECISION,
                intangible_assets DOUBLE PRECISION,
                other_assets  DOUBLE PRECISION,
                accounts_payable DOUBLE PRECISION,
                short_term_debt DOUBLE PRECISION,
                other_current_liab DOUBLE PRECISION,
                long_term_debt DOUBLE PRECISION,
                other_liab    DOUBLE PRECISION,
                retained_earnings DOUBLE PRECISION,
                total_stockholder_equity DOUBLE PRECISION,
                net_tangible_assets DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # TTM Income Statement
        cur.execute("DROP TABLE IF EXISTS income_statement_ttm;")
        cur.execute("""
            CREATE TABLE income_statement_ttm (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_revenue  DOUBLE PRECISION,
                cost_of_revenue DOUBLE PRECISION,
                gross_profit   DOUBLE PRECISION,
                research_development DOUBLE PRECISION,
                selling_general_admin DOUBLE PRECISION,
                operating_expenses DOUBLE PRECISION,
                operating_income DOUBLE PRECISION,
                interest_expense DOUBLE PRECISION,
                total_other_income DOUBLE PRECISION,
                income_before_tax DOUBLE PRECISION,
                income_tax_expense DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                ebitda       DOUBLE PRECISION,
                ebit         DOUBLE PRECISION,
                basic_eps     DOUBLE PRECISION,
                diluted_eps   DOUBLE PRECISION,
                shares_outstanding DOUBLE PRECISION,
                shares_diluted DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # TTM Cash Flow
        cur.execute("DROP TABLE IF EXISTS cash_flow_ttm;")
        cur.execute("""
            CREATE TABLE cash_flow_ttm (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                operating_cashflow DOUBLE PRECISION,
                capital_expenditure DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                depreciation  DOUBLE PRECISION,
                change_in_working_capital DOUBLE PRECISION,
                change_in_receivables DOUBLE PRECISION,
                change_in_inventory DOUBLE PRECISION,
                change_in_account_payables DOUBLE PRECISION,
                other_operating_cashflow DOUBLE PRECISION,
                investing_cashflow DOUBLE PRECISION,
                financing_cashflow DOUBLE PRECISION,
                dividend_paid DOUBLE PRECISION,
                stock_sale_repurchase DOUBLE PRECISION,
                net_borrowings DOUBLE PRECISION,
                other_financing_cashflow DOUBLE PRECISION,
                effect_of_forex_changes DOUBLE PRECISION,
                net_change_in_cash DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Financials (Annual)
        cur.execute("DROP TABLE IF EXISTS financials;")
        cur.execute("""
            CREATE TABLE financials (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                total_revenue  DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                operating_cashflow DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Financials (Quarterly)
        cur.execute("DROP TABLE IF EXISTS financials_quarterly;")
        cur.execute("""
            CREATE TABLE financials_quarterly (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                total_revenue  DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                operating_cashflow DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Financials (TTM)
        cur.execute("DROP TABLE IF EXISTS financials_ttm;")
        cur.execute("""
            CREATE TABLE financials_ttm (
                id              SERIAL PRIMARY KEY,
                symbol         VARCHAR(10) NOT NULL,
                date           DATE NOT NULL,
                total_assets   DOUBLE PRECISION,
                total_liab     DOUBLE PRECISION,
                cash          DOUBLE PRECISION,
                total_revenue  DOUBLE PRECISION,
                net_income    DOUBLE PRECISION,
                operating_cashflow DOUBLE PRECISION,
                free_cashflow DOUBLE PRECISION,
                fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, date)
            );
        """)

        # Create indexes for faster lookups
        for table in [
            'balance_sheet_annual', 'balance_sheet_quarterly', 'balance_sheet_ttm',
            'income_statement_annual', 'income_statement_quarterly', 'income_statement_ttm',
            'cash_flow_annual', 'cash_flow_quarterly', 'cash_flow_ttm',
            'financials', 'financials_quarterly', 'financials_ttm'
        ]:
            cur.execute(f"""
                CREATE INDEX idx_{table}_symbol 
                ON {table} (symbol);
            """)

        # Ensure last_updated table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
                script_name VARCHAR(255) PRIMARY KEY,
                last_run    TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()

def check_tables_exist(conn, required_tables):
    """Check that all required tables exist in the current database/schema."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public';
        """)
        existing = {row[0] for row in cur.fetchall()}
    missing = [t for t in required_tables if t not in existing]
    if missing:
        logger.error(f"Missing required tables after creation: {missing}")
        return False
    return True

@retry(max_attempts=3, initial_delay=2, backoff=2)
def process_symbol(symbol, conn):
    """Process only balance sheet annual and quarterly for a single symbol"""
    yf_symbol = symbol.upper().replace(".", "-")
    ticker = yf.Ticker(yf_symbol)
    bs_annual = ticker.get_balance_sheet()
    bs_quarterly = ticker.quarterly_balance_sheet

    with conn.cursor() as cur:
        # Insert Annual Balance Sheet
        if not bs_annual.empty:
            for date, row in bs_annual.items():
                try:
                    cur.execute("""
                        INSERT INTO balance_sheet_annual (
                            symbol, date, total_assets, total_liab, cash,
                            short_term_investments, net_receivables, inventory,
                            other_current_assets, total_current_assets,
                            long_term_investments, property_plant_equipment,
                            goodwill, intangible_assets, other_assets,
                            accounts_payable, short_term_debt, other_current_liab,
                            long_term_debt, other_liab, retained_earnings,
                            total_stockholder_equity, net_tangible_assets
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                                 %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            total_assets = EXCLUDED.total_assets,
                            total_liab = EXCLUDED.total_liab,
                            fetched_at = NOW();
                    """, [symbol, date] + [clean_value(row.get(col)) for col in [
                        'Total Assets', 'Total Liab', 'Cash',
                        'Short Term Investments', 'Net Receivables', 'Inventory',
                        'Other Current Assets', 'Total Current Assets',
                        'Long Term Investments', 'Property Plant Equipment',
                        'Goodwill', 'Intangible Assets', 'Other Assets',
                        'Accounts Payable', 'Short Term Debt', 'Other Current Liab',
                        'Long Term Debt', 'Other Liab', 'Retained Earnings',
                        'Total Stockholder Equity', 'Net Tangible Assets'
                    ]])
                except Exception as e:
                    logger.error(f"Error inserting annual balance sheet for {symbol}: {e}")

        # Insert Quarterly Balance Sheet
        if not bs_quarterly.empty:
            for date, row in bs_quarterly.items():
                try:
                    cur.execute("""
                        INSERT INTO balance_sheet_quarterly (
                            symbol, date, total_assets, total_liab, cash,
                            short_term_investments, net_receivables, inventory,
                            other_current_assets, total_current_assets,
                            long_term_investments, property_plant_equipment,
                            goodwill, intangible_assets, other_assets,
                            accounts_payable, short_term_debt, other_current_liab,
                            long_term_debt, other_liab, retained_earnings,
                            total_stockholder_equity, net_tangible_assets
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                                 %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date) DO UPDATE SET
                            total_assets = EXCLUDED.total_assets,
                            total_liab = EXCLUDED.total_liab,
                            fetched_at = NOW();
                    """, [symbol, date] + [clean_value(row.get(col)) for col in [
                        'Total Assets', 'Total Liab', 'Cash',
                        'Short Term Investments', 'Net Receivables', 'Inventory',
                        'Other Current Assets', 'Total Current Assets',
                        'Long Term Investments', 'Property Plant Equipment',
                        'Goodwill', 'Intangible Assets', 'Other Assets',
                        'Accounts Payable', 'Short Term Debt', 'Other Current Liab',
                        'Long Term Debt', 'Other Liab', 'Retained Earnings',
                        'Total Stockholder Equity', 'Net Tangible Assets'
                    ]])
                except Exception as e:
                    logger.error(f"Error inserting quarterly balance sheet for {symbol}: {e}")

    conn.commit()

def update_last_run(conn):
    """Stamp the last run time in last_updated."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

def main():
    """
    Main workflow for loading financial data:
    1. Drop and create all required tables
    2. Check all required tables exist
    3. Fetch all symbols
    4. For each symbol, fetch and insert data
    """
    conn = None
    import gc
    # List of all tables that must exist for the workflow
    required_tables = [
        'balance_sheet_annual', 'balance_sheet_quarterly', 'balance_sheet_ttm',
        'income_statement_annual', 'income_statement_quarterly', 'income_statement_ttm',
        'cash_flow_annual', 'cash_flow_quarterly', 'cash_flow_ttm',
        'financials', 'financials_quarterly', 'financials_ttm', 'last_updated'
    ]

    logger.info("==============================")
    logger.info("Starting loadfinancialdata.py")
    logger.info(f"Process PID: {os.getpid()}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Memory usage at start: {get_rss_mb():.1f} MB RSS")
    logger.info(f"DB_SECRET_ARN: {DB_SECRET_ARN}")
    logger.info("==============================")

    try:
        # --- Step 1: Connect to DB ---
        user, pwd, host, port, dbname = get_db_config()
        logger.info(f"Connecting to DB at {host}:{port} db={dbname} user={user}")
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=pwd,
            dbname=dbname,
            sslmode="require",
            cursor_factory=DictCursor
        )
        conn.set_session(autocommit=False)

        # --- Step 2: Drop and create all tables ---
        logger.info("Dropping and creating all financial tables before data load...")
        try:
            ensure_tables(conn)
            logger.info("Table creation complete.")
        except Exception as e:
            logger.exception("Error creating tables. Exiting.")
            if conn:
                conn.rollback()
                conn.close()
            sys.exit(1)

        # --- Step 3: Check all required tables exist ---
        if not check_tables_exist(conn, required_tables):
            logger.error("Table creation failed or tables missing. Exiting.")
            if conn:
                conn.rollback()
                conn.close()
            sys.exit(1)

        # --- Step 4: Fetch all symbols ---
        log_mem("Before fetching symbols")
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT symbol 
                FROM stock_symbols 
                ORDER BY symbol;
            """)
            symbols = [r["symbol"] for r in cur.fetchall()]
        log_mem("After fetching symbols")

        # --- Step 5: For each symbol, fetch and insert data ---
        total_symbols = len(symbols)
        processed = 0
        failed = 0
        start_time = time.time()

        for sym in symbols:
            try:
                log_mem(f"Processing {sym} ({processed + 1}/{total_symbols})")
                process_symbol(sym, conn)
                conn.commit()
                processed += 1
                # Explicitly delete large objects and collect garbage
                gc.collect()
                # Adaptive sleep based on memory usage
                if get_rss_mb() > 800:  # Lower threshold for small ECS
                    time.sleep(0.5)
                else:
                    time.sleep(0.05)
            except Exception:
                logger.exception(f"Failed to process {sym}")
                try:
                    conn.rollback()
                except Exception:
                    logger.exception("Error during conn.rollback() after failure")
                failed += 1
                if failed > total_symbols * 0.2:
                    logger.error("Too many failures, stopping process")
                    break

        update_last_run(conn)
        elapsed = time.time() - start_time
        logger.info(f"Completed processing {processed}/{total_symbols} symbols with {failed} failures in {elapsed:.1f} seconds")
        log_mem("End of main loop")

    except Exception:
        logger.exception("Fatal error in main()")
        if conn:
            try:
                conn.rollback()
            except Exception:
                logger.exception("Error during conn.rollback() after fatal error")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                logger.exception("Error closing database connection")
        log_mem("End of script")
        logger.info("loadfinancialdata complete.")

if __name__ == "__main__":
    main()
