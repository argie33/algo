#!/usr/bin/env python3
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
from datetime import datetime, timedelta

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
# Date settings
# -------------------------------
CURRENT_DATE = datetime.now().date()
PREVIOUS_DATE = CURRENT_DATE - timedelta(days=1)

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES   = 3
RETRY_DELAY         = 0.2   # seconds between download retries

# -------------------------------
# Price-daily columns
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

# -------------------------------
# Main loader with batched inserts/updates
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted = 0
    failed = []
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
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=True,
                    actions=True,
                    threads=True,
                    progress=False
                )
                break
            except Exception as e:
                logging.warning(f"{table_name} download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            logging.error(f"{table_name} batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} attempts")
            failed += batch
            continue

        log_mem(f"{table_name} after yf.download")
        cur.execute("SELECT 1;")   # ping DB

        # ─── Batch-insert/update per symbol ─────────────────────
        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                # extract sub-DataFrame for this symbol
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

                # fetch existing dates for this symbol
                cur.execute(f"SELECT date FROM {table_name} WHERE symbol = %s", (orig_sym,))
                existing_dates = set([r["date"] for r in cur.fetchall()])

                # build rows for new or stale dates (missing, previous, or current)
                rows_to_process = []
                for idx, row in sub.iterrows():
                    date_val = idx.date()
                    if date_val == PREVIOUS_DATE or date_val == CURRENT_DATE or date_val not in existing_dates:
                        rows_to_process.append([
                            orig_sym,
                            date_val,
                            None if math.isnan(row["Open"])      else float(row["Open"]),
                            None if math.isnan(row["High"])      else float(row["High"]),
                            None if math.isnan(row["Low"])       else float(row["Low"]),
                            None if math.isnan(row["Close"])     else float(row["Close"]),
                            None if math.isnan(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"])),
                            None if math.isnan(row["Volume"])    else int(row["Volume"]),
                            0.0  if ("Dividends" not in row or math.isnan(row["Dividends"])) else float(row["Dividends"]),
                            0.0  if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"])
                        ])

                if not rows_to_process:
                    logging.info(f"{orig_sym}: no new or updated rows; skipping")
                    continue

                # delete any existing rows for these dates to allow upsert
                dates_set  = set(r[1] for r in rows_to_process)
                dates_list = sorted(dates_set)
                placeholder = ','.join(['%s'] * len(dates_list))
                delete_sql = f"DELETE FROM {table_name} WHERE symbol = %s AND date IN ({placeholder})"
                cur.execute(delete_sql, [orig_sym] + dates_list)

                # insert fresh rows
                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                execute_values(cur, sql, rows_to_process)
                conn.commit()
                inserted += len(rows_to_process)
                logging.info(f"{table_name} — {orig_sym}: upserted {len(rows_to_process)} rows")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
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

    # Ensure tables exist (no drops, so data is preserved)
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
    conn.commit()

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_daily", stock_syms, cur, conn)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_daily", etf_syms, cur, conn)

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
    logging.info(f"Stocks — total: {t_s}, upserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, upserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()

    logging.info("All done.")
