#!/usr/bin/env python3
# Monthly price data loader - fetches monthly OHLCV data for all symbols
# Trigger deploy-app-stocks workflow test - monthly loader update v13 - API key encryption secret added to Lambda environment
import sys
import time
import logging
import json
import os
import gc
import resource
import math

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadpricemonthly.py"
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
RATE_LIMIT_BASE_DELAY = 5   # fixed 5-second delay for rate limits

# -------------------------------
# Price-monthly columns
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
COL_LIST     = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    # Try local environment first
    if os.environ.get("DB_HOST"):
        return {
            "host":   os.environ.get("DB_HOST", "localhost"),
            "port":   int(os.environ.get("DB_PORT", 5432)),
            "user":   os.environ.get("DB_USER", "stocks"),
            "password": os.environ.get("DB_PASSWORD", "bed0elAn"),
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
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download full history ──────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    period="max",
                    interval="1mo",
                    group_by="ticker",
                    auto_adjust=False,   # FIXED: Match TradingView unadjusted prices
                    actions=True,        # preserved
                    threads=True,        # preserved
                    progress=False,      # preserved
                    timeout=60           # increased from default 10s to handle slow connections
                )
                break
            except Exception as e:
                logging.warning(f"{table_name} download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            # Fallback: try downloading each symbol individually with retry logic
            logging.info(f"{table_name} batch {batch_idx+1} - attempting per-symbol download as fallback")
            per_symbol_results = {}
            for orig_sym in batch:
                symbol_success = False
                last_error = None
                for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                    try:
                        single_df = yf.download(orig_sym, period="max", interval="1mo", auto_adjust=False, actions=True, progress=False, timeout=60)
                        if not single_df.empty:
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
                        if "Too Many Requests" in error_msg or "Rate limit" in error_msg:
                            delay = RATE_LIMIT_BASE_DELAY
                            logging.warning(f"{table_name} — {orig_sym}: rate limited (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), waiting {delay}s")
                            time.sleep(delay)
                        elif "Timeout" in error_msg:
                            logging.warning(f"{table_name} — {orig_sym}: timeout (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                            time.sleep(3)
                        elif "Period" in error_msg and "invalid" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: invalid period - skipping")
                            break
                        elif "delisted" in error_msg or "no price data" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: delisted - skipping")
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
                    sub = df[yq_sym] if len(yq_batch) > 1 else df
                except KeyError:
                    logging.warning(f"No data for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()
                sub = sub[sub["Open"].notna()]
                if sub.empty:
                    logging.warning(f"No valid price rows for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                rows = []
                for idx, row in sub.iterrows():
                    rows.append([
                        orig_sym,
                        idx.date(),
                        None if math.isnan(row["Open"])      else float(row["Open"]),
                        None if math.isnan(row["High"])      else float(row["High"]),
                        None if math.isnan(row["Low"])       else float(row["Low"]),
                        None if math.isnan(row["Close"])     else float(row["Close"]),
                        None if math.isnan(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"])),
                        None if math.isnan(row["Volume"])    else int(row["Volume"]),
                        0.0  if ("Dividends" not in row or (isinstance(row["Dividends"], float) and math.isnan(row["Dividends"]))) else (0.0 if not isinstance(row["Dividends"], (int, float)) else float(row["Dividends"])),
                        0.0  if ("Stock Splits" not in row or (isinstance(row["Stock Splits"], float) and math.isnan(row["Stock Splits"]))) else (0.0 if not isinstance(row["Stock Splits"], (int, float)) else float(row["Stock Splits"]))
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
                    single_df = yf.download(orig_sym, period="max", interval="1mo", auto_adjust=False, actions=True, progress=False, timeout=60)
                    if not single_df.empty:
                        # Now insert this data into database
                        rows = []
                        single_df = single_df.sort_index()
                        single_df = single_df[single_df["Open"].notna()]
                        for idx, row in single_df.iterrows():
                            rows.append([
                                orig_sym,
                                idx.date(),
                                None if math.isnan(row["Open"])      else float(row["Open"]),
                                None if math.isnan(row["High"])      else float(row["High"]),
                                None if math.isnan(row["Low"])       else float(row["Low"]),
                                None if math.isnan(row["Close"])     else float(row["Close"]),
                                None if math.isnan(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"])),
                                None if math.isnan(row["Volume"])    else int(row["Volume"]),
                                0.0  if ("Dividends" not in row or math.isnan(row["Dividends"])) else float(row["Dividends"]),
                                0.0  if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"])
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
                        time.sleep(3)
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
    try:
        log_mem("startup")
        logging.info("Starting pricemonthly loader...")

        # Connect to DB with timeout
        cfg  = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"],
            connect_timeout=30
        )
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recreate tables
        logging.info("Recreating price_monthly table…")
        cur.execute("DROP TABLE IF EXISTS price_monthly;")
        cur.execute("""
            CREATE TABLE price_monthly (
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

        logging.info("Recreating etf_price_monthly table…")
        cur.execute("DROP TABLE IF EXISTS etf_price_monthly;")
        cur.execute("""
            CREATE TABLE etf_price_monthly (
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

        logging.info("Recreating price_monthly_etf table…")
        cur.execute("DROP TABLE IF EXISTS price_monthly_etf;")
        cur.execute("""
            CREATE TABLE price_monthly_etf (
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
        conn.commit()

        # Load stock symbols
        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        t_s, i_s, f_s = load_prices("price_monthly", stock_syms, cur, conn)

        # Load all ETF symbols (from etf_symbols table)
        cur.execute("SELECT symbol FROM etf_symbols;")
        all_etf_syms = [r["symbol"] for r in cur.fetchall()]
        t_w, i_w, f_w = load_prices("etf_price_monthly", all_etf_syms, cur, conn)

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
        logging.info("All done. Exiting successfully.")
        sys.exit(0)
        
    except KeyError as e:
        logging.error(f"Missing environment variable: {e}")
        sys.exit(1)
    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)
