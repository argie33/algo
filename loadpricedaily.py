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
from psycopg2.extras import RealDictCursor
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
MAX_INSERT_RETRIES  = 3
INSERT_RETRY_DELAY  = 0.2  # seconds between insert retries

# -------------------------------
# Price-daily columns & SQL helpers
# -------------------------------
PRICE_COLUMNS = [
    "date", "open", "high", "low", "close",
    "adj_close", "volume", "dividends", "stock_splits"
]
PLACEHOLDERS = ", ".join(["%s"] * (len(PRICE_COLUMNS) + 1))
COL_LIST     = ", ".join(["symbol"] + PRICE_COLUMNS)

def insert_stock_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    cursor.execute(
        f"INSERT INTO price_daily ({COL_LIST}) VALUES ({PLACEHOLDERS});",
        vals
    )

def insert_etf_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    cursor.execute(
        f"INSERT INTO etf_price_daily ({COL_LIST}) VALUES ({PLACEHOLDERS});",
        vals
    )

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":     sec["host"],
        "port":     int(sec.get("port", 5432)),
        "user":     sec["username"],
        "password": sec["password"],
        "dbname":   sec["dbname"]
    }

# -------------------------------
# Main loader
# -------------------------------
def load_prices(table_name, symbols, insert_fn, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE : (batch_idx+1)*CHUNK_SIZE]
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
                    auto_adjust=False,
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

        # ─── Insert every historical row per symbol ─────────────
        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                try:
                    sub = df[yq_sym] if len(yq_batch) > 1 else df
                except KeyError:
                    logging.warning(f"No data for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                if sub.empty:
                    logging.warning(f"No data for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()
                sub = sub[sub["Open"].notna()]
                if sub.empty:
                    logging.warning(f"No valid price rows for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                symbol_inserted = 0
                for idx, row in sub.iterrows():
                    rec = {
                        "date":         idx.date(),
                        "open":         float(row["Open"]) if not math.isnan(row["Open"]) else None,
                        "high":         float(row["High"]) if not math.isnan(row["High"]) else None,
                        "low":          float(row["Low"]) if not math.isnan(row["Low"]) else None,
                        "close":        float(row["Close"]) if not math.isnan(row["Close"]) else None,
                        "adj_close":    float(row.get("Adj Close", row["Close"])) if not math.isnan(row.get("Adj Close", row["Close"])) else None,
                        "volume":       int(row["Volume"]) if not math.isnan(row["Volume"]) else None,
                        "dividends":    float(row["Dividends"]) if ("Dividends" in row and not math.isnan(row["Dividends"])) else 0.0,
                        "stock_splits": float(row["Stock Splits"]) if ("Stock Splits" in row and not math.isnan(row["Stock Splits"])) else 0.0
                    }

                    for i in range(1, MAX_INSERT_RETRIES+1):
                        try:
                            insert_fn(cur, orig_sym, rec)
                            conn.commit()
                            cur.execute("SELECT 1;")
                            symbol_inserted += 1
                            break
                        except Exception as ie:
                            conn.rollback()
                            if i < MAX_INSERT_RETRIES:
                                logging.warning(
                                    f"{orig_sym} {rec['date']} insert failed "
                                    f"(attempt {i}/{MAX_INSERT_RETRIES}): {ie}; retrying…"
                                )
                                time.sleep(INSERT_RETRY_DELAY)
                            else:
                                logging.error(
                                    f"{orig_sym} {rec['date']} insert failed after "
                                    f"{MAX_INSERT_RETRIES} attempts: {ie}",
                                    exc_info=True
                                )
                                failed.append(orig_sym)

                inserted += symbol_inserted
                logging.info(f"{table_name} — {orig_sym}: inserted {symbol_inserted} rows")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, inserted, failed

if __name__ == "__main__":
    log_mem("startup")

    # 1) Connect to DB
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 2) Recreate price_daily table
    logging.info("Recreating price_daily table…")
    log_mem("before stock DDL")
    cur.execute("DROP TABLE IF EXISTS price_daily;")
    cur.execute("""
    CREATE TABLE price_daily (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(10) NOT NULL,
        date         DATE NOT NULL,
        open         DOUBLE PRECISION,
        high         DOUBLE PRECISION,
        low          DOUBLE PRECISION,
        close        DOUBLE PRECISION,
        adj_close    DOUBLE PRECISION,
        volume       BIGINT,
        dividends    DOUBLE PRECISION,
        stock_splits DOUBLE PRECISION,
        fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 3) Recreate etf_price_daily table
    logging.info("Recreating etf_price_daily table…")
    log_mem("before etf DDL")
    cur.execute("DROP TABLE IF EXISTS etf_price_daily;")
    cur.execute("""
    CREATE TABLE etf_price_daily (
        id           SERIAL PRIMARY KEY,
        symbol       VARCHAR(10) NOT NULL,
        date         DATE NOT NULL,
        open         DOUBLE PRECISION,
        high         DOUBLE PRECISION,
        low          DOUBLE PRECISION,
        close        DOUBLE PRECISION,
        adj_close    DOUBLE PRECISION,
        volume       BIGINT,
        dividends    DOUBLE PRECISION,
        stock_splits DOUBLE PRECISION,
        fetched_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    # 4) Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_daily", stock_syms, insert_stock_price, cur, conn)

    # 5) Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_daily", etf_syms, insert_etf_price, cur, conn)

    # 6) Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    # 7) Final summary & shutdown
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, inserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.")
