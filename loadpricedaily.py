#!/usr/bin/env python3
# Trigger: 20260101_102914 - Load all data to AWS RDS
# Daily price data loader - fetches OHLCV data for all symbols
# CRITICAL: Database has 0 price records. Must run to populate price_daily table for all pages/APIs
# TRIGGER: 2025-10-27 - Loading price history for volatility, beta, Sharpe ratio calculations
# Trigger: 20251225-AWS-RUN - Load price data to populate frontend (AWS deployment)
import sys
import time
import logging
import json
import os
import gc
import resource
import math
import argparse

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadpricedaily.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES   = 3
RETRY_DELAY         = 0.2   # seconds between download retries
MAX_SYMBOL_RETRIES  = 5     # retries for individual symbols
RATE_LIMIT_BASE_DELAY = 5   # start with 5 seconds, increases dynamically

# -------------------------------
# Price-daily columns
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
COL_LIST     = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader - supports both AWS and local environment
# -------------------------------
def get_db_config():
    # Try local environment first
    if os.environ.get("DB_HOST"):
        return {
            "host":   os.environ.get("DB_HOST", "localhost"),
            "port":   int(os.environ.get("DB_PORT", 5432)),
            "user":   os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

    # Fall back to AWS Secrets Manager if available
    if os.environ.get("DB_SECRET_ARN"):
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host":   sec["host"],
            "port":   int(sec.get("port", 5432)),
            "user":   sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }

    # Final fallback to localhost defaults
    return {
        "host":   "localhost",
        "port":   5432,
        "user":   "stocks",
        "password": "bed0elAn",
        "dbname": "stocks"
    }

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted, failed = 0, []
    timeout_failures = []  # Track timeouts separately for end-of-load retry
    CHUNK_SIZE, PAUSE = 20, 1.0  # Increased from 0.1s to 1.0s to avoid yfinance rate limiting
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    # Skip if no symbols to load
    if total == 0:
        logging.info(f"No symbols to load for {table_name}")
        return 0, 0, []

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        # Handle preferred shares (symbols with $): use base ticker for yfinance
        yq_batch = []
        for s in batch:
            if '$' in s:
                # CADE$A -> CADE (use base ticker for preferred shares)
                base_ticker = s.split('$')[0]
                yq_batch.append(base_ticker)
            else:
                # Normal ticker conversion
                yq_batch.append(s.replace('.', '-').upper())
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download full history ──────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    period=DATA_PERIOD,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,    # preserved
                    actions=True,        # preserved
                    threads=True,        # preserved
                    progress=False       # preserved
                )
                logging.info(f"Downloaded dataframe for {yq_batch}: {df.shape if hasattr(df, 'shape') else type(df)}")
                break
            except Exception as e:
                logging.warning(f"{table_name} download failed (attempt {attempt}/{MAX_BATCH_RETRIES}): {e}")
                time.sleep(RETRY_DELAY)
                if attempt == MAX_BATCH_RETRIES:
                    logging.warning(f"{table_name} batch {batch_idx+1} failed all attempts - will retry per-symbol")
                    df = None
        else:
            df = None

        if df is None:
            # Fallback: try downloading each symbol individually with retry logic
            logging.info(f"{table_name} batch {batch_idx+1} - attempting per-symbol download as fallback")
            per_symbol_results = {}
            for orig_sym in batch:
                symbol_success = False
                last_error = None
                for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                    try:
                        single_df = yf.download(orig_sym, period=DATA_PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False)
                        if not single_df.empty:
                            # CRITICAL FIX: Normalize column names to lowercase (yfinance returns uppercase)
                            single_df.columns = [col.lower() for col in single_df.columns]
                            per_symbol_results[orig_sym] = single_df
                            symbol_success = True
                            last_error = None
                            break
                        else:
                            logging.warning(f"{table_name} — {orig_sym}: no data (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                            last_error = "no_data"
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(1)
                    except Exception as e:
                        error_msg = str(e)
                        last_error = error_msg
                        # Check if it's a rate limit error
                        if "Too Many Requests" in error_msg or "Rate limit" in error_msg:
                            # Use simple fixed delay (research shows 2-5s works best)
                            delay = RATE_LIMIT_BASE_DELAY
                            logging.warning(f"{table_name} — {orig_sym}: rate limited (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), waiting {delay}s")
                            time.sleep(delay)
                        elif "Timeout" in error_msg:
                            logging.warning(f"{table_name} — {orig_sym}: timeout (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                            time.sleep(5)
                        elif "Period" in error_msg and "invalid" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: invalid period (test symbol) - skipping")
                            break
                        elif "delisted" in error_msg or "no price data" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: delisted/no data - skipping")
                            break
                        else:
                            logging.warning(f"{table_name} — {orig_sym}: error (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}): {e}")
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(2)

                if not symbol_success:
                    # Track timeout failures separately for end-of-load retry
                    if last_error and "Timeout" in str(last_error):
                        timeout_failures.append(orig_sym)
                    else:
                        failed.append(orig_sym)

            if per_symbol_results:
                df = per_symbol_results
            else:
                logging.error(f"{table_name} batch {batch_idx+1} failed completely - all symbols skipped")
                failed += batch
                continue

        log_mem(f"{table_name} after yf.download")
        cur.execute("SELECT 1;")   # ping DB

        # ─── Batch-insert per symbol ─────────────────────────────
        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                try:
                    # Handle both single and multi-ticker dataframes
                    if len(yq_batch) > 1:
                        # Batch download returns MultiIndex columns (ticker, OHLCV)
                        if yq_sym in df.columns.get_level_values(0):
                            sub = df[yq_sym]
                        else:
                            logging.warning(f"No data for {orig_sym}; skipping")
                            failed.append(orig_sym)
                            continue
                    else:
                        # Single ticker download
                        sub = df
                except (KeyError, AttributeError) as e:
                    logging.warning(f"No data for {orig_sym}: {e}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()
                # CRITICAL FIX: Normalize ALL column names to lowercase (yfinance returns UPPERCASE from both batch and per-symbol downloads)
                # This handles both formats:
                # - Batch downloads with MultiIndex: extract right side of tuple and lowercase
                # - Single downloads with flat columns: already strings, just lowercase them
                normalized_cols = {}
                for col in sub.columns:
                    if isinstance(col, tuple):
                        # MultiIndex case: col is like ('Open',) or ('High',), extract and lowercase
                        normalized_cols[col] = col[1].lower() if len(col) > 1 else str(col[0]).lower()
                    else:
                        # Regular string case: just lowercase it
                        normalized_cols[col] = str(col).lower()

                # Apply the normalization by renaming the dataframe columns
                sub = sub.rename(columns=normalized_cols)

                # Verify that 'open' column exists after normalization
                if "open" not in sub.columns:
                    logging.warning(f"No 'open' column found for {orig_sym}; available columns: {list(sub.columns)}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub[sub["open"].notna()]
                if sub.empty:
                    logging.warning(f"No valid price rows for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                rows = []
                for idx, row in sub.iterrows():
                    rows.append([
                        orig_sym,
                        idx.date(),
                        None if math.isnan(row["open"])      else float(row["open"]),
                        None if math.isnan(row["high"])      else float(row["high"]),
                        None if math.isnan(row["low"])       else float(row["low"]),
                        None if math.isnan(row["close"])     else float(row["close"]),
                        None if math.isnan(row.get("adj close", row["close"])) else float(row.get("adj close", row["close"])),
                        None if math.isnan(row["volume"])    else int(row["volume"]),
                        0.0  if ("dividends" not in row or math.isnan(row["dividends"])) else float(row["dividends"]),
                        0.0  if ("stock splits" not in row or math.isnan(row["stock splits"])) else float(row["stock splits"])
                    ])

                if not rows:
                    logging.warning(f"{orig_sym}: no rows after cleaning; skipping")
                    failed.append(orig_sym)
                    continue

                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                execute_values(cur, sql, rows)
                conn.commit()
                inserted += len(rows)
                logging.info(f"{table_name} — {orig_sym}: batch-inserted {len(rows)} rows")
            if inserted == 0:
                logging.warning(f"{table_name}: No rows inserted for batch {batch_idx+1}")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    # ─── End-of-load retry for timeout failures ──────────────────────────────
    if timeout_failures:
        logging.info(f"{table_name} – retrying {len(timeout_failures)} timeout failures at end of load: {timeout_failures}")
        for orig_sym in timeout_failures:
            symbol_success = False
            for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                try:
                    single_df = yf.download(orig_sym, period=DATA_PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False)
                    if not single_df.empty:
                        # Normalize column names to lowercase
                        single_df.columns = [col.lower() for col in single_df.columns]
                        # Now insert this data into database
                        rows = []
                        single_df = single_df.sort_index()
                        single_df = single_df[single_df["open"].notna()]
                        for idx, row in single_df.iterrows():
                            rows.append([
                                orig_sym,
                                idx.date(),
                                None if math.isnan(row["open"])      else float(row["open"]),
                                None if math.isnan(row["high"])      else float(row["high"]),
                                None if math.isnan(row["low"])       else float(row["low"]),
                                None if math.isnan(row["close"])     else float(row["close"]),
                                None if math.isnan(row.get("adj close", row["close"])) else float(row.get("adj close", row["close"])),
                                None if math.isnan(row["volume"])    else int(row["volume"]),
                                0.0  if ("dividends" not in row or math.isnan(row["dividends"])) else float(row["dividends"]),
                                0.0  if ("stock splits" not in row or math.isnan(row["stock splits"])) else float(row["stock splits"])
                            ])
                        if rows:
                            sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                            execute_values(cur, sql, rows)
                            conn.commit()
                            inserted += len(rows)
                            logging.info(f"{table_name} — {orig_sym} (RETRY): batch-inserted {len(rows)} rows")
                            symbol_success = True
                            break
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: still no data on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(2)
                except Exception as e:
                    error_msg = str(e)
                    if "Timeout" in error_msg:
                        logging.warning(f"{table_name} — {orig_sym}: timeout on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        time.sleep(5)
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: error on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}): {e}")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(2)
            if not symbol_success:
                failed.append(orig_sym)
                logging.error(f"{table_name} — {orig_sym}: FAILED on retry - moving to failed list")

    return total, inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Load daily price data for stocks and ETFs')
    parser.add_argument('--historical', action='store_true', 
                       help='Load full historical data (period="max")')
    parser.add_argument('--incremental', action='store_true',
                       help='Load recent data only (period="3mo")')
    args = parser.parse_args()

    # Determine data period based on arguments
    if args.historical:
        DATA_PERIOD = "max"
        logging.info("Running in HISTORICAL mode - loading full historical data")
    elif args.incremental:
        DATA_PERIOD = "3mo"
        logging.info("Running in INCREMENTAL mode - loading recent 3 months of data")
    else:
        DATA_PERIOD = "max"  # Default to full history
        logging.info("Running in DEFAULT mode - loading full historical data")

    log_mem("startup")

    # Connect to DB
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create tables if they don't exist (don't drop - allow incremental loading)
    logging.info("Ensuring price_daily table exists…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_daily (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(10) NOT NULL,
            date         DATE         NOT NULL,
            open         DOUBLE PRECISION,
            high         DOUBLE PRECISION,
            low          DOUBLE PRECISION,
            close        DOUBLE PRECISION,
            adj_close    DOUBLE PRECISION,
            volume       BIGINT,
            dividends    DOUBLE PRECISION,
            stock_splits DOUBLE PRECISION,
            fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create index for efficient lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);")

    logging.info("Ensuring etf_price_daily table exists…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etf_price_daily (
            id           SERIAL PRIMARY KEY,
            symbol       VARCHAR(10) NOT NULL,
            date         DATE         NOT NULL,
            open         DOUBLE PRECISION,
            high         DOUBLE PRECISION,
            low          DOUBLE PRECISION,
            close        DOUBLE PRECISION,
            adj_close    DOUBLE PRECISION,
            volume       BIGINT,
            dividends    DOUBLE PRECISION,
            stock_splits DOUBLE PRECISION,
            fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Create index for efficient lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol ON etf_price_daily(symbol);")

    conn.commit()

    # Load stock symbols - only ones not already in price_daily
    cur.execute("SELECT symbol FROM stock_symbols;")
    all_stock_syms = [r["symbol"] for r in cur.fetchall()]

    # Get symbols that already have price data
    cur.execute("SELECT DISTINCT symbol FROM price_daily;")
    loaded_stock_syms = {r["symbol"] for r in cur.fetchall()}

    # Filter to only missing symbols
    stock_syms = [s for s in all_stock_syms if s not in loaded_stock_syms]
    logging.info(f"Total stock symbols: {len(all_stock_syms)}, already loaded: {len(loaded_stock_syms)}, remaining: {len(stock_syms)}")

    t_s, i_s, f_s = load_prices("price_daily", stock_syms, cur, conn)

    # Load all ETF symbols (from etf_symbols table if it exists) - only ones not already in etf_price_daily
    try:
        cur.execute("SELECT symbol FROM etf_symbols;")
        all_etf_syms = [r["symbol"] for r in cur.fetchall()]

        # Get ETF symbols that already have price data
        cur.execute("SELECT DISTINCT symbol FROM etf_price_daily;")
        loaded_etf_syms = {r["symbol"] for r in cur.fetchall()}

        # Filter to only missing ETF symbols
        etf_syms = [s for s in all_etf_syms if s not in loaded_etf_syms]
        logging.info(f"Total ETF symbols: {len(all_etf_syms)}, already loaded: {len(loaded_etf_syms)}, remaining: {len(etf_syms)}")

        t_w, i_w, f_w = load_prices("etf_price_daily", etf_syms, cur, conn)
    except psycopg2.errors.UndefinedTable:
        logging.warning("⚠️ etf_symbols table does not exist - skipping ETF price loading")
        t_w, i_w, f_w = 0, 0, 0

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks      — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs        — total: {t_w}, inserted: {i_w}, failed: {len(f_w)}")

    cur.close()
    conn.close()
    logging.info("All done.")
# Deploy trigger 20251219
