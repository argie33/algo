#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import math
import gc
import resource              # ← standard library for RSS
from datetime import datetime

from yahooquery import Ticker
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"
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
    # Linux: kilobytes; macOS: bytes
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    mb = get_rss_mb()
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

# -------------------------------
# Clean NaNs in place
# -------------------------------
def clean_row(rec):
    for k, v in list(rec.items()):
        if isinstance(v, float) and math.isnan(v):
            rec[k] = None
    return rec

# -------------------------------
# Batch insert helper
# -------------------------------
FIN_DATA_COLUMNS = [
    "symbol","maxAge","currentPrice","targetHighPrice","targetLowPrice",
    "targetMeanPrice","targetMedianPrice","recommendationMean","recommendationKey",
    "numberOfAnalystOpinions","totalCash","totalCashPerShare","ebitda","totalDebt",
    "quickRatio","currentRatio","totalRevenue","debtToEquity","revenuePerShare",
    "returnOnAssets","returnOnEquity","grossProfits","freeCashflow","operatingCashflow",
    "earningsGrowth","revenueGrowth","grossMargins","ebitdaMargins","operatingMargins",
    "profitMargins","financialCurrency"
]
PLACEHOLDERS = ", ".join(["%s"] * len(FIN_DATA_COLUMNS))
COL_LIST    = ", ".join(FIN_DATA_COLUMNS)

def insert_fin_data(cursor, rec, symbol):
    vals = [symbol] + [rec.get(col) for col in FIN_DATA_COLUMNS[1:]]
    sql = f"INSERT INTO financial_data ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # 1) Load DB creds and open connection
    secret_arn = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    conn = psycopg2.connect(
        host=sec["host"], port=int(sec["port"]),
        user=sec["username"], password=sec["password"],
        dbname=sec["dbname"], sslmode="require"
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 2) (Re)create financial_data table
    logging.info("Recreating financial_data table…")
    log_mem("before DDL")
    cur.execute("DROP TABLE IF EXISTS financial_data;")
    cur.execute(f"""
    CREATE TABLE financial_data (
      symbol               VARCHAR(20) PRIMARY KEY,
      maxAge               INT,
      currentPrice         DOUBLE PRECISION,
      targetHighPrice      DOUBLE PRECISION,
      targetLowPrice       DOUBLE PRECISION,
      targetMeanPrice      DOUBLE PRECISION,
      targetMedianPrice    DOUBLE PRECISION,
      recommendationMean   DOUBLE PRECISION,
      recommendationKey    VARCHAR(20),
      numberOfAnalystOpinions INT,
      totalCash            DOUBLE PRECISION,
      totalCashPerShare    DOUBLE PRECISION,
      ebitda               DOUBLE PRECISION,
      totalDebt            DOUBLE PRECISION,
      quickRatio           DOUBLE PRECISION,
      currentRatio         DOUBLE PRECISION,
      totalRevenue         DOUBLE PRECISION,
      debtToEquity         DOUBLE PRECISION,
      revenuePerShare      DOUBLE PRECISION,
      returnOnAssets       DOUBLE PRECISION,
      returnOnEquity       DOUBLE PRECISION,
      grossProfits         DOUBLE PRECISION,
      freeCashflow         DOUBLE PRECISION,
      operatingCashflow    DOUBLE PRECISION,
      earningsGrowth       DOUBLE PRECISION,
      revenueGrowth        DOUBLE PRECISION,
      grossMargins         DOUBLE PRECISION,
      ebitdaMargins        DOUBLE PRECISION,
      operatingMargins     DOUBLE PRECISION,
      profitMargins        DOUBLE PRECISION,
      financialCurrency    VARCHAR(10),
      fetched_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """)
    log_mem("after DDL")

    # 3) Fetch all symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    symbols = [row[0] for row in cur.fetchall()]
    mapping = {s.upper().replace('.', '-'): s for s in symbols}
    total_symbols = len(symbols)
    log_mem("after fetching symbols")

    # prepare counters
    inserted = 0
    failed = []

    # 4) Process in small batches with GC tuning
    CHUNK_SIZE = 10    # tune to your RAM
    PAUSE      = 0.1   # tune to avoid API 429s
    total_batches = (total_symbols + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * CHUNK_SIZE
        end   = min(start + CHUNK_SIZE, total_symbols)
        batch = symbols[start:end]
        yq_batch = [s.upper().replace('.', '-') for s in batch]

        logging.info(f"Batch {batch_idx+1}/{total_batches}: symbols {start+1}–{end}")
        log_mem(f"batch {batch_idx+1} start")

        try:
            ticker = Ticker(yq_batch)
            data   = ticker.financial_data
        except Exception as e:
            logging.error(f"Ticker fetch failed for batch {batch_idx+1}: {e}", exc_info=True)
            failed.extend(batch)
            continue

        log_mem("after Ticker load")

        gc.disable()
        try:
            for yq_sym, rec in data.items():
                orig = mapping.get(yq_sym)
                if not orig:
                    logging.warning(f"No mapping for '{yq_sym}'; skipping")
                    failed.append(yq_sym)
                    continue

                if not isinstance(rec, dict):
                    logging.warning(f"Bad record for '{orig}': {rec!r}")
                    failed.append(orig)
                    continue

                rec = clean_row(rec)
                logging.info(f"Processing {orig}")
                try:
                    insert_fin_data(cur, rec, orig)
                    logging.info(f"Inserted data for {orig}")
                    inserted += 1
                except Exception as ex:
                    logging.error(f"Insert failed for {orig}: {ex}", exc_info=True)
                    failed.append(orig)
        finally:
            gc.enable()

        # teardown & pause
        del data, ticker, batch, yq_batch
        gc.collect()
        log_mem(f"batch {batch_idx+1} end")
        time.sleep(PAUSE)

    # 5) Update last_run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    log_mem("after last_updated")

    # 6) Final peak memory log & summary
    peak_mb = get_rss_mb()
    logging.info(f"[MEM] peak RSS during run: {peak_mb:.1f} MB")
    logging.info(f"Total symbols: {total_symbols}, inserted: {inserted}, failed: {len(failed)}")
    if failed:
        logging.warning("Failed symbols: %s", ", ".join(failed[:50]) + ("…" if len(failed)>50 else ""))

    cur.close()
    conn.close()
    logging.info("All symbols processed.")
