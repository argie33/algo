#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import math
import gc
from datetime import datetime

import psutil
from yahooquery import Ticker
import boto3
import psycopg2

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadkeystats.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory‐logging helper
# -------------------------------
_process = psutil.Process()
def log_mem(stage: str):
    mb = _process.memory_info().rss / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

# -------------------------------
# Timestamp parsing without pandas
# -------------------------------
def parse_ts(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value)
        except:
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except:
            try:
                return datetime.utcfromtimestamp(float(value))
            except:
                return None
    return None

# -------------------------------
# Nullify NaNs in place
# -------------------------------
def clean_row(rec):
    for k, v in list(rec.items()):
        if isinstance(v, float) and math.isnan(v):
            rec[k] = None
    return rec

# -------------------------------
# Batch insert helper
# -------------------------------
KEY_STATS_COLUMNS = [
    "symbol","maxAge","priceHint","enterpriseValue","forwardPE","profitMargins",
    "floatShares","sharesOutstanding","sharesShort","sharesShortPriorMonth",
    "sharesShortPreviousMonthDate","dateShortInterest","sharesPercentSharesOut",
    "heldPercentInsiders","heldPercentInstitutions","shortRatio","shortPercentOfFloat",
    "beta","category","bookValue","priceToBook","fundFamily","legalType",
    "lastFiscalYearEnd","nextFiscalYearEnd","mostRecentQuarter","earningsQuarterlyGrowth",
    "netIncomeToCommon","trailingEps","forwardEps","pegRatio","lastSplitFactor",
    "lastSplitDate","enterpriseToRevenue","enterpriseToEbitda","week52Change","sp52WeekChange"
]
PLACEHOLDERS = ", ".join(["%s"] * len(KEY_STATS_COLUMNS))
COL_LIST    = ", ".join(KEY_STATS_COLUMNS)

def insert_key_stats(cursor, rec, symbol):
    vals = [symbol] + [rec.get(col) for col in KEY_STATS_COLUMNS[1:]]
    sql = f"INSERT INTO key_stats ({COL_LIST}) VALUES ({PLACEHOLDERS});"
    cursor.execute(sql, vals)

# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # 1) Load DB creds once
    secret_arn = os.environ["DB_SECRET_ARN"]
    sm = boto3.client("secretsmanager")
    sec = json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])
    conn = psycopg2.connect(
        host=sec["host"], port=int(sec["port"]),
        user=sec["username"], password=sec["password"],
        dbname=sec["dbname"]
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 2) (Re)create key_stats table
    logging.info("Recreating key_stats table…")
    log_mem("before DDL")
    cur.execute("DROP TABLE IF EXISTS key_stats;")
    cur.execute(f"""
    CREATE TABLE key_stats (
        id SERIAL PRIMARY KEY,
        maxAge DOUBLE PRECISION,
        priceHint DOUBLE PRECISION,
        enterpriseValue DOUBLE PRECISION,
        forwardPE DOUBLE PRECISION,
        profitMargins DOUBLE PRECISION,
        floatShares DOUBLE PRECISION,
        sharesOutstanding DOUBLE PRECISION,
        sharesShort DOUBLE PRECISION,
        sharesShortPriorMonth DOUBLE PRECISION,
        sharesShortPreviousMonthDate TIMESTAMP,
        dateShortInterest TIMESTAMP,
        sharesPercentSharesOut DOUBLE PRECISION,
        heldPercentInsiders DOUBLE PRECISION,
        heldPercentInstitutions DOUBLE PRECISION,
        shortRatio DOUBLE PRECISION,
        shortPercentOfFloat DOUBLE PRECISION,
        beta DOUBLE PRECISION,
        category VARCHAR(50),
        bookValue DOUBLE PRECISION,
        priceToBook DOUBLE PRECISION,
        fundFamily VARCHAR(100),
        legalType VARCHAR(100),
        lastFiscalYearEnd TIMESTAMP,
        nextFiscalYearEnd TIMESTAMP,
        mostRecentQuarter TIMESTAMP,
        earningsQuarterlyGrowth DOUBLE PRECISION,
        netIncomeToCommon DOUBLE PRECISION,
        trailingEps DOUBLE PRECISION,
        forwardEps DOUBLE PRECISION,
        pegRatio DOUBLE PRECISION,
        lastSplitFactor VARCHAR(20),
        lastSplitDate TIMESTAMP,
        enterpriseToRevenue DOUBLE PRECISION,
        enterpriseToEbitda DOUBLE PRECISION,
        week52Change DOUBLE PRECISION,
        sp52WeekChange DOUBLE PRECISION,
        symbol VARCHAR(10),
        fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    log_mem("after DDL")

    # 3) Fetch all symbols
    cur.execute("SELECT symbol FROM stock_symbols;")
    symbols = [row[0] for row in cur.fetchall()]
    mapping = {s.replace('.', '-').lower(): s for s in symbols}
    log_mem("after fetching symbols")

    # 4) Process in small batches with GC tuning
    CHUNK_SIZE = 5    # adjust to your available memory
    PAUSE      = 0.1  # adjust to your rate-limit budget
    ts_fields = [
        "sharesShortPreviousMonthDate","dateShortInterest",
        "lastFiscalYearEnd","nextFiscalYearEnd",
        "mostRecentQuarter","lastSplitDate"
    ]

    total_batches = (len(symbols) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(total_batches):
        start = i * CHUNK_SIZE
        end   = start + CHUNK_SIZE
        batch    = symbols[start:end]
        yq_batch = [s.replace('.', '-').lower() for s in batch]

        logging.info(f"Batch {i+1}/{total_batches}: symbols {start+1}–{min(end,len(symbols))}")
        log_mem(f"batch {i+1} start")

        # fetch from Yahooquery
        ticker = Ticker(yq_batch)
        data   = ticker.key_stats
        log_mem(f"after Ticker load")

        # tight insert loop with GC off
        gc.disable()
        try:
            for yq, rec in data.items():
                orig = mapping.get(yq)
                if not orig or not isinstance(rec, dict):
                    continue
                for fld in ts_fields:
                    rec[fld] = parse_ts(rec.get(fld))
                rec = clean_row(rec)
                insert_key_stats(cur, rec, orig)
        finally:
            gc.enable()

        # teardown and collect
        del data, ticker, batch, yq_batch
        gc.collect()
        log_mem(f"batch {i+1} end")

        time.sleep(PAUSE)

    # 5) Update last_run
    cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    log_mem("just before exit")

    cur.close()
    conn.close()
    logging.info("All symbols processed.")
