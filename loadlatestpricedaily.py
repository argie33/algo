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
from psycopg2.errors import DuplicateTable
from datetime import datetime, date, timedelta

import boto3
import yfinance as yf

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadlatestpricedaily.py"
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
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2   # seconds between download retries

# -------------------------------
# Price-daily columns
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
ALL_COLUMNS = ["symbol"] + PRICE_COLUMNS + ["fetched_at"]
COL_LIST    = ", ".join(ALL_COLUMNS)

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
# Upsert helper
# -------------------------------
def upsert_rows(table_name, rows, cur, conn):
    sql = f"""
      INSERT INTO {table_name} ({COL_LIST})
        VALUES %s
      ON CONFLICT (symbol, date) DO UPDATE
        SET open         = EXCLUDED.open,
            high         = EXCLUDED.high,
            low          = EXCLUDED.low,
            close        = EXCLUDED.close,
            adj_close    = EXCLUDED.adj_close,
            volume       = EXCLUDED.volume,
            dividends    = EXCLUDED.dividends,
            stock_splits = EXCLUDED.stock_splits,
            fetched_at   = EXCLUDED.fetched_at
    """
    execute_values(cur, sql, rows)
    conn.commit()

# -------------------------------
# Load & upsert price data for a date-range
# -------------------------------
def load_prices_range(table_name, symbols, cur, conn, start_date, end_date):
    total = len(symbols)
    logging.info(f"{table_name}: loading {total} symbols for {start_date} to {end_date}")
    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download date range ──────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
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

        # ─── Upsert per symbol ────────────────────────────────
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
                fetched_at = datetime.now()
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
                        0.0  if ("Dividends" not in row or math.isnan(row["Dividends"]))     else float(row["Dividends"]),
                        0.0  if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"]),
                        fetched_at
                    ])

                if not rows:
                    logging.warning(f"{orig_sym}: no rows after cleaning; skipping")
                    failed.append(orig_sym)
                    continue

                upsert_rows(table_name, rows, cur, conn)
                inserted += len(rows)
                logging.info(f"{table_name} — {orig_sym}: upserted {len(rows)} rows")
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

    # ─── Ensure unique constraints for UPSERT ───────────────
    for tbl in ("price_daily", "etf_price_daily"):
        constraint = f"uq_{tbl}_symbol_date"
        try:
            cur.execute(
                f"ALTER TABLE {tbl} "
                f"ADD CONSTRAINT {constraint} UNIQUE(symbol, date)"
            )
            logging.info(f"Created constraint {constraint} on {tbl}")
        except DuplicateTable:
            logging.debug(f"Constraint {constraint} already exists on {tbl}, skipping")
    conn.commit()

    # Prepare date ranges
    today     = date.today()
    yesterday = today - timedelta(days=1)
    tomorrow  = today + timedelta(days=1)

    # Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]

    # Phase 1: finalize yesterday
    logging.info("Finalizing yesterday's stock data…")
    t_sy, i_sy, f_sy = load_prices_range("price_daily", stock_syms, cur, conn, yesterday, today)

    # Phase 2: refresh today
    logging.info("Refreshing today's stock data…")
    t_st, i_st, f_st = load_prices_range("price_daily", stock_syms, cur, conn, today, tomorrow)

    # Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]

    # Phase 1: finalize yesterday for ETFs
    logging.info("Finalizing yesterday's ETF data…")
    t_ey, i_ey, f_ey = load_prices_range("etf_price_daily", etf_syms, cur, conn, yesterday, today)

    # Phase 2: refresh today for ETFs
    logging.info("Refreshing today's ETF data…")
    t_et, i_et, f_et = load_prices_range("etf_price_daily", etf_syms, cur, conn, today, tomorrow)

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    # Final logs
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(
        f"Stocks — yesterday: total {t_sy}, upserted {i_sy}, failed {len(f_sy)}; "
        f"today: total {t_st}, upserted {i_st}, failed {len(f_st)}"
    )
    logging.info(
        f"ETFs   — yesterday: total {t_ey}, upserted {i_ey}, failed {len(f_ey)}; "
        f"today: total {t_et}, upserted {i_et}, failed {len(f_et)}"
    )

    cur.close()
    conn.close()
    logging.info("All done.")
