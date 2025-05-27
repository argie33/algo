#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
import pandas as pd

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime, timedelta

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadpricedaily_incremental.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2  # seconds between download retries

# -------------------------------
# Price-daily columns
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
COL_LIST = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret = boto3.client("secretsmanager") \
                  .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Batched-incremental loader
# -------------------------------
def load_prices_incremental(table_name, symbols, cur, conn):
    total = len(symbols)
    logger.info(f"Loading {table_name} incrementally: {total} symbols")

    # Fetch each symbol’s last_date in one query
    cur.execute(f"SELECT symbol, MAX(date) AS last_date FROM {table_name} GROUP BY symbol;")
    last_dates = {r['symbol']: r['last_date'] for r in cur.fetchall()}

    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch_syms = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        logger.info(f"{table_name} batch {batch_idx+1}/{batches} symbols: {batch_syms}")

        yq_tickers = [s.replace('.', '-').replace('$','-').upper() for s in batch_syms]
        batch_failed = []
        symbol_row_counts = {}

        # decide full vs incremental for the batch
        existing_dates = [last_dates.get(s) for s in batch_syms if last_dates.get(s)]
        if existing_dates:
            start_date = min(existing_dates)
            dl_kwargs = {
                "tickers":     yq_tickers,
                "start":       start_date.isoformat(),
                "end":         (datetime.now().date() + timedelta(days=1)).isoformat(),
                "interval":    "1d",
                "group_by":    "ticker",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logger.info(f"{table_name} batch {batch_idx+1}/{batches}: incremental from {start_date}")
        else:
            dl_kwargs = {
                "tickers":     yq_tickers,
                "period":      "max",
                "interval":    "1d",
                "group_by":    "ticker",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logger.info(f"{table_name} batch {batch_idx+1}/{batches}: full download")

        # download with retries
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logger.info(f"{table_name} – batch {batch_idx+1}: download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} download start")
            try:
                df = yf.download(**dl_kwargs)
                break
            except Exception as e:
                logger.warning(f"download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            logger.error(f"batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} attempts")
            failed.extend(batch_syms)
            batch_failed.extend(batch_syms)
            continue

        log_mem(f"{table_name} after download")

        # build rows, track per-symbol counts
        rows = []
        for i, orig_sym in enumerate(batch_syms):
            logger.info(f"{table_name} – {orig_sym}: processing")
            yq_sym = yq_tickers[i]
            try:
                sub = df[yq_sym] if len(yq_tickers) > 1 else df
            except KeyError:
                logger.warning(f"{orig_sym}: no data returned; skipping")
                failed.append(orig_sym)
                batch_failed.append(orig_sym)
                symbol_row_counts[orig_sym] = 0
                continue

            sub = sub.sort_index()
            sub = sub[sub["Open"].notna()]

            last = last_dates.get(orig_sym)
            if last:
                # include last_date to refresh current period
                sub = sub[sub.index.date >= last]

            count = len(sub)
            symbol_row_counts[orig_sym] = count
            if count == 0:
                logger.info(f"{orig_sym}: no new or updated rows")
                continue

            logger.info(f"{orig_sym}: {count} rows to upsert")
            for ts, row in sub.iterrows():
                rows.append([
                    orig_sym,
                    ts.date(),
                    None if pd.isna(row["Open"])      else float(row["Open"]),
                    None if pd.isna(row["High"])      else float(row["High"]),
                    None if pd.isna(row["Low"])       else float(row["Low"]),
                    None if pd.isna(row["Close"])     else float(row["Close"]),
                    None if pd.isna(row.get("Adj Close", row["Close"])) 
                        else float(row.get("Adj Close", row["Close"])),
                    None if pd.isna(row["Volume"])    else int(row["Volume"]),
                    0.0  if pd.isna(row.get("Dividends", 0.0)) 
                        else float(row.get("Dividends", 0.0)),
                    0.0  if pd.isna(row.get("Stock Splits", 0.0)) 
                        else float(row.get("Stock Splits", 0.0))
                ])

        # single upsert per batch
        if rows:
            sql = f"""
INSERT INTO {table_name} ({COL_LIST})
VALUES %s
ON CONFLICT (symbol, date) DO UPDATE SET
    open         = EXCLUDED.open,
    high         = EXCLUDED.high,
    low          = EXCLUDED.low,
    close        = EXCLUDED.close,
    adj_close    = EXCLUDED.adj_close,
    volume       = EXCLUDED.volume,
    dividends    = EXCLUDED.dividends,
    stock_splits = EXCLUDED.stock_splits,
    fetched_at   = NOW()
"""
            execute_values(cur, sql, rows)
            conn.commit()
            inserted += len(rows)
            logger.info(f"{table_name} batch {batch_idx+1}/{batches}: upserted {len(rows)} rows")

        # batch summary
        succeeded = [s for s, c in symbol_row_counts.items() if c > 0]
        skipped   = [s for s, c in symbol_row_counts.items() if c == 0]
        logger.info(
            f"{table_name} batch {batch_idx+1}/{batches} summary – "
            f"succeeded ({len(succeeded)}): {succeeded}; "
            f"skipped ({len(skipped)}): {skipped}; "
            f"failed ({len(batch_failed)}): {batch_failed}"
        )

        # cleanup
        del df, rows
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    cfg  = get_db_config()
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1) Remove duplicates so we can build a unique index
    logger.info("Deduplicating price_daily…")
    cur.execute("""
WITH ranked AS (
  SELECT ctid,
         ROW_NUMBER() OVER (PARTITION BY symbol, date ORDER BY ctid) AS rn
  FROM price_daily
)
DELETE FROM price_daily
WHERE ctid IN (SELECT ctid FROM ranked WHERE rn > 1);
""")
    logger.info("Deduplicating etf_price_daily…")
    cur.execute("""
WITH ranked AS (
  SELECT ctid,
         ROW_NUMBER() OVER (PARTITION BY symbol, date ORDER BY ctid) AS rn
  FROM etf_price_daily
)
DELETE FROM etf_price_daily
WHERE ctid IN (SELECT ctid FROM ranked WHERE rn > 1);
""")
    conn.commit()

    # 2) Create unique indexes for ON CONFLICT
    logger.info("Creating unique indexes…")
    cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS price_daily_symbol_date_idx
  ON price_daily(symbol, date);
CREATE UNIQUE INDEX IF NOT EXISTS etf_price_daily_symbol_date_idx
  ON etf_price_daily(symbol, date);
""")
    conn.commit()

    # 3) Run the batched incremental loader
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices_incremental("price_daily", stock_syms, cur, conn)

    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices_incremental("etf_price_daily", etf_syms, cur, conn)

    # 4) Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logger.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logger.info(f"Stocks — total: {t_s}, upserted: {i_s}, failed: {len(f_s)}")
    logger.info(f"ETFs   — total: {t_e}, upserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logger.info("All done.")
