#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import gc
import resource
from datetime import datetime

import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
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
    mb = get_rss_mb()
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

# -------------------------------
# Batch-level retry config
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 2   # seconds between retries

# -------------------------------
# Price-monthly columns & SQL helpers
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close","adj_close","volume"
]
PLACEHOLDERS  = ", ".join(["%s"] * (len(PRICE_COLUMNS) + 1))  # +1 for symbol
COL_LIST      = ", ".join(["symbol"] + PRICE_COLUMNS)

def insert_stock_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    sql = f"INSERT INTO price_monthly ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

def insert_etf_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    sql = f"INSERT INTO etf_price_monthly ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_arn = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # 1) Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 2) (Re)create both tables
    logging.info("Recreating price_monthly table…")
    log_mem("before stock DDL")
    cur.execute("DROP TABLE IF EXISTS price_monthly;")
    cur.execute("""
    CREATE TABLE price_monthly (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        adj_close DOUBLE PRECISION,
        volume BIGINT,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    log_mem("after stock DDL")

    logging.info("Recreating etf_price_monthly table…")
    log_mem("before etf DDL")
    cur.execute("DROP TABLE IF EXISTS etf_price_monthly;")
    cur.execute("""
    CREATE TABLE etf_price_monthly (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        date DATE NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        adj_close DOUBLE PRECISION,
        volume BIGINT,
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    log_mem("after etf DDL")

    # -------------------------------
    # Helper to process a list of tickers into a given insert function
    # -------------------------------
    def load_prices(table_name, symbols, insert_fn):
        total = len(symbols)
        logging.info(f"Loading {table_name}: {total} symbols")
        inserted = 0
        failed = []

        CHUNK_SIZE = 20
        PAUSE      = 0.1
        total_batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

        for batch_idx in range(total_batches):
            start = batch_idx * CHUNK_SIZE
            end   = min(start + CHUNK_SIZE, total)
            batch = symbols[start:end]

            # normalize tickers
            yq_batch = [s.replace('.', '-').replace('$', '-').upper() for s in batch]
            mapping  = dict(zip(yq_batch, batch))

            # retry download
            for attempt in range(1, MAX_BATCH_RETRIES + 1):
                logging.info(f"{table_name} – batch {batch_idx+1}/{total_batches}, attempt {attempt}")
                log_mem(f"{table_name} batch {batch_idx+1} start")
                try:
                    df = yf.download(
                        tickers=yq_batch,
                        period="1d",
                        group_by="ticker",
                        auto_adjust=False,
                        threads=True,
                        progress=False
                    )
                    break
                except Exception as e:
                    logging.warning(f"{table_name} batch download failed: {e}; retrying in {RETRY_DELAY}s…")
                    time.sleep(RETRY_DELAY)
            else:
                logging.error(f"{table_name} batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} attempts")
                failed.extend(batch)
                continue

            log_mem(f"{table_name} after yf.download")

            # insert per symbol
            gc.disable()
            try:
                for yq_sym, orig_sym in mapping.items():
                    try:
                        sub = df[yq_sym] if len(yq_batch) > 1 else df
                        if sub.empty:
                            logging.warning(f"No data for {orig_sym}; skipping")
                            failed.append(orig_sym)
                            continue

                        last = sub.iloc[-1]
                        rec = {
                            "date":      last.name.date(),
                            "open":      float(last["Open"]),
                            "high":      float(last["High"]),
                            "low":       float(last["Low"]),
                            "close":     float(last["Close"]),
                            "adj_close": float(last.get("Adj Close", last["Close"])),
                            "volume":    int(last["Volume"])
                        }

                        insert_fn(cur, orig_sym, rec)
                        logging.info(f"Inserted {table_name} for {orig_sym}")
                        inserted += 1

                    except Exception as e:
                        logging.error(f"Insert failed for {orig_sym}: {e}", exc_info=True)
                        failed.append(orig_sym)
            finally:
                gc.enable()

            # teardown & pause
            del df, batch, yq_batch, mapping
            gc.collect()
            log_mem(f"{table_name} batch {batch_idx+1} end")
            time.sleep(PAUSE)

        return total, inserted, failed

    # 3) Fetch & load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [row["symbol"] for row in cur.fetchall()]
    t_stock, i_stock, f_stock = load_prices("price_monthly", stock_syms, insert_stock_price)

    # 4) Fetch & load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [row["symbol"] for row in cur.fetchall()]
    t_etf, i_etf, f_etf = load_prices("etf_price_monthly", etf_syms, insert_etf_price)

    # 5) Update last_run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))

    # 6) Final summary & memory
    peak_mb = get_rss_mb()
    logging.info(f"[MEM] peak RSS during run: {peak_mb:.1f} MB")
    logging.info(f"Stock symbols – total: {t_stock}, inserted: {i_stock}, failed: {len(f_stock)}")
    if f_stock:
        logging.warning("Failed stock symbols: %s",
                        ", ".join(f_stock[:50]) + ("…" if len(f_stock) > 50 else ""))

    logging.info(f"ETF symbols   – total: {t_etf}, inserted: {i_etf}, failed: {len(f_etf)}")
    if f_etf:
        logging.warning("Failed ETF symbols: %s",
                        ", ".join(f_etf[:50]) + ("…" if len(f_etf) > 50 else ""))

    cur.close()
    conn.close()
    logging.info("All done.")
