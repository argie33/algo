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
# Memory‐logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2   # seconds between yf.download retries

# -------------------------------
# Columns for INSERT
# -------------------------------
PRICE_COLUMNS = [
    "date", "open", "high", "low",
    "close", "adj_close", "volume",
    "dividends", "stock_splits"
]
COL_LIST = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    sec = json.loads(
        boto3.client("secretsmanager")
             .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Main loader with skipping & batched inserts
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    # 1) Skip any symbols already in the existing table
    cur.execute(
        f"SELECT DISTINCT symbol FROM {table_name} WHERE symbol = ANY(%s);",
        (symbols,)
    )
    loaded = {row["symbol"] for row in cur.fetchall()}
    to_load = [s for s in symbols if s not in loaded]
    logging.info(
        f"{table_name}: {len(to_load)} new symbols to load;"
        f" skipping {len(loaded)} already present"
    )
    if not to_load:
        return 0, 0, []

    # 2) Chunk & download
    total, inserted, failed = len(to_load), 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch   = to_load[batch_idx*CHUNK_SIZE : (batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.strip().upper() for s in batch]
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download history ───────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    period="max",
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    actions=True,     # include dividends & splits
                    threads=True,
                    progress=False
                )
                break
            except Exception as e:
                logging.warning(f"Download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            logging.error(f"Batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} attempts")
            failed += batch
            continue

        log_mem(f"{table_name} after yf.download")
        cur.execute("SELECT 1;")  # ping

        # ─── Batch‐insert per symbol ─────────────────────────
        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                sub = df[yq_sym] if len(yq_batch) > 1 else df
                # drop any missing‐Open rows
                sub = sub[sub["Open"].notna()]
                if sub.empty:
                    logging.warning(f"No data for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()
                rows = []
                for idx, row in sub.iterrows():
                    rows.append((
                        orig_sym,
                        idx.date(),
                        None if math.isnan(row["Open"]) else float(row["Open"]),
                        None if math.isnan(row["High"]) else float(row["High"]),
                        None if math.isnan(row["Low"]) else float(row["Low"]),
                        None if math.isnan(row["Close"]) else float(row["Close"]),
                        None if math.isnan(row.get("Adj Close", row["Close"])) 
                             else float(row.get("Adj Close", row["Close"])),
                        None if math.isnan(row["Volume"]) else int(row["Volume"]),
                        0.0  if ("Dividends" not in row or math.isnan(row["Dividends"])) 
                             else float(row["Dividends"]),
                        0.0  if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) 
                             else float(row["Stock Splits"])
                    ))

                if not rows:
                    logging.warning(f"{orig_sym}: no valid rows after cleaning; skipping")
                    failed.append(orig_sym)
                    continue

                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                execute_values(cur, sql, rows)
                conn.commit()
                inserted += len(rows)
                logging.info(f"{table_name} — {orig_sym}: batch‐inserted {len(rows)} rows")
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

    # 1) Connect to the database
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 2) Load stock symbols, skipping any already in price_daily
    cur.execute("SELECT symbol FROM stock_symbols;")
    stocks = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_daily", stocks, cur, conn)

    # 3) Load ETF symbols, skipping any already in etf_price_daily
    cur.execute("SELECT symbol FROM etf_symbols;")
    etfs = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_daily", etfs, cur, conn)

    # 4) Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    # 5) Summary & shutdown
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, inserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.")
