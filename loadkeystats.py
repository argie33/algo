#!/usr/bin/env python3
import sys
import time
import logging
import json
import os
import math
import gc
import resource
from datetime import datetime

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
# Memory‐logging helper (RSS in MB)
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
# Batch‐level retry config
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 5   # seconds between retries on Invalid Crumb

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

    # 2) (Re)create key_stats table with explicit DDL
    logging.info("Recreating key_stats table…")
    log_mem("before DDL")
    cur.execute("DROP TABLE IF EXISTS key_stats;")
    cur.execute("""
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
    total = len(symbols)
    log_mem("after fetching symbols")

    # Prepare counters
    inserted = 0
    failed = []

    # 4) Process in small batches with GC tuning + retry
    CHUNK_SIZE = 10    # tweak to your memory
    PAUSE      = 0.1   # tweak to your rate limits
    ts_fields = [
        "sharesShortPreviousMonthDate","dateShortInterest",
        "lastFiscalYearEnd","nextFiscalYearEnd",
        "mostRecentQuarter","lastSplitDate"
    ]
    total_batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * CHUNK_SIZE
        end   = min(start + CHUNK_SIZE, total)
        batch = symbols[start:end]
        yq_batch = [s.replace('.', '-').lower() for s in batch]

        # Batch‐level retry loop
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"Batch {batch_idx+1}/{total_batches} – attempt {attempt}")
            log_mem(f"batch {batch_idx+1} attempt {attempt} start")

            ticker = Ticker(yq_batch)
            data   = ticker.key_stats

            # Detect “Invalid Crumb”
            if any(isinstance(rec, str) and "Invalid Crumb" in rec for rec in data.values()):
                logging.warning(f"Invalid Crumb in batch {batch_idx+1}, retrying in {RETRY_DELAY}s…")
                try:
                    ticker._session.cookies.clear()
                except Exception:
                    pass
                time.sleep(RETRY_DELAY)
                continue

            # No crumb error → proceed
            break
        else:
            # All attempts failed
            logging.error(f"Batch {batch_idx+1} failed after {MAX_BATCH_RETRIES} attempts")
            failed.extend(batch)
            continue

        log_mem("after Ticker load")

        # Per-symbol insert
        gc.disable()
        try:
            for yq, rec in data.items():
                orig = mapping.get(yq)
                if not orig:
                    logging.warning(f"No mapping for '{yq}'; skipping")
                    failed.append(yq)
                    continue

                if not isinstance(rec, dict):
                    logging.warning(f"Bad record for '{orig}': {rec!r}")
                    failed.append(orig)
                    continue

                for fld in ts_fields:
                    rec[fld] = parse_ts(rec.get(fld))

                rec = clean_row(rec)

                try:
                    insert_key_stats(cur, rec, orig)
                    logging.info(f"Inserted key_stats for {orig}")
                    inserted += 1
                except Exception as e:
                    logging.error(f"Insert failed for {orig}: {e}", exc_info=True)
                    failed.append(orig)
        finally:
            gc.enable()

        # Teardown & pause
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

    # 6) Final peak memory log & summary
    peak_mb = get_rss_mb()
    logging.info(f"[MEM] peak RSS during run: {peak_mb:.1f} MB")
    logging.info(f"Total symbols: {total}, inserted: {inserted}, failed: {len(failed)}")
    if failed:
        logging.warning("Failed symbols: %s", ", ".join(failed[:50]) + ("…" if len(failed) > 50 else ""))

    cur.close()
    conn.close()
    logging.info("All done.")
