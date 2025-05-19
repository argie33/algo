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
SCRIPT_NAME = "loadpricemonthy.py"
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
RETRY_DELAY       = 2  # seconds between download retries

# -------------------------------
# Insert-level retry config
# -------------------------------
MAX_INSERT_RETRIES   = 3
INSERT_RETRY_DELAY   = 1  # seconds between insert retries

# -------------------------------
# Price-monthy columns & SQL helpers
# -------------------------------
PRICE_COLUMNS = [
    "date", "open", "high", "low", "close", "adj_close", "volume"
]
PLACEHOLDERS = ", ".join(["%s"] * (len(PRICE_COLUMNS) + 1))
COL_LIST     = ", ".join(["symbol"] + PRICE_COLUMNS)

def insert_stock_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    sql = f"INSERT INTO price_monthy ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

def insert_etf_price(cursor, symbol, rec):
    vals = [symbol] + [rec[col] for col in PRICE_COLUMNS]
    sql = f"INSERT INTO etf_price_monthy ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    secret_arn = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
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
        batch = symbols[batch_idx*CHUNK_SIZE : (batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$', '-').upper() for s in batch]
        mapping  = dict(zip(yq_batch, batch))

        # Download with retry
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
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
                logging.warning(f"{table_name} download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            logging.error(f"{table_name} batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} download attempts")
            failed += batch
            continue

        log_mem(f"{table_name} after yf.download")

        # Ping DB to catch dropped connections
        cur.execute("SELECT 1;")

        # Insert per symbol with its own retry loop
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

                last = sub.iloc[-1]
                rec = {
                    "date":      last.name.date(),
                    "open":      float(last["Open"]),
                    "high":      float(last["High"]),
                    "low":       float(last["Low"]),
                    "close":     float(last["Close"]),
                    "adj_close": float(last.get("Adj Close", last["Close"])),
                    "volume":    int(last["Volume"]) if not math.isnan(last["Volume"]) else None
                }

                # insert retry loop
                for i_attempt in range(1, MAX_INSERT_RETRIES+1):
                    try:
                        insert_fn(cur, orig_sym, rec)
                        conn.commit()
                        # ping DB before logging success
                        cur.execute("SELECT 1;")
                        logging.info(f"Inserted {table_name} for {orig_sym}")
                        inserted += 1
                        break
                    except Exception as ie:
                        conn.rollback()
                        if i_attempt < MAX_INSERT_RETRIES:
                            logging.warning(
                                f"Insert failed for {orig_sym} (attempt {i_attempt}/{MAX_INSERT_RETRIES}): {ie}; retrying in {INSERT_RETRY_DELAY}s"
                            )
                            time.sleep(INSERT_RETRY_DELAY)
                        else:
                            logging.error(
                                f"Insert failed for {orig_sym} after {MAX_INSERT_RETRIES} attempts: {ie}",
                                exc_info=True
                            )
                            failed.append(orig_sym)
                # end insert retry
        finally:
            gc.enable()

        # Cleanup & pause
        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    return total, inserted, failed

if __name__ == "__main__":
    log_mem("startup")

    # 1) Connect to DB
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 2) (Re)create tables & commit
    logging.info("Recreating price_monthy table…")
    log_mem("before stock DDL")
    cur.execute("DROP TABLE IF EXISTS price_monthy;")
    cur.execute("""
    CREATE TABLE price_monthy (
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

    logging.info("Recreating etf_price_monthy table…")
    log_mem("before etf DDL")
    cur.execute("DROP TABLE IF EXISTS etf_price_monthy;")
    cur.execute("""
    CREATE TABLE etf_price_monthy (
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
    conn.commit()

    # 3) Load stock symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [row["symbol"] for row in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_monthy", stock_syms, insert_stock_price, cur, conn)

    # 4) Load ETF symbols
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [row["symbol"] for row in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_monthy", etf_syms, insert_etf_price, cur, conn)

    # 5) Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    # 6) Final summary & shutdown
    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, inserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.")
