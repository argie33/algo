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
# Memory‐logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage/1024 if sys.platform.startswith("linux") else usage/(1024*1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2  # seconds between download retries

# -------------------------------
# Price‐daily columns
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
    sec_str = boto3.client("secretsmanager") \
                   .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(sec_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

# -------------------------------
# Batched‐incremental loader w/ 10‐day check + missing‐data reload
# -------------------------------
def load_prices_incremental(table_name, symbols, cur, conn):
    total = len(symbols)
    logger.info(f"Loading {table_name} incrementally: {total} symbols")

    # 1) Gather last_date + earliest_of_last_10 for each symbol
    cur.execute(f"""
WITH ranked AS (
  SELECT symbol, date,
         ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
  FROM {table_name}
)
SELECT symbol,
       MAX(date) AS last_date,
       MIN(CASE WHEN rn <= 10 THEN date END) AS earliest_recheck
FROM ranked
GROUP BY symbol;
""")
    info = {r['symbol']: (r['last_date'], r['earliest_recheck']) for r in cur.fetchall()}

    inserted, failed = 0, []
    CHUNK_SIZE, PAUSE = 20, 0.1
    batches = (total + CHUNK_SIZE - 1)//CHUNK_SIZE

    for b in range(batches):
        batch = symbols[b*CHUNK_SIZE:(b+1)*CHUNK_SIZE]
        logger.info(f"{table_name} batch {b+1}/{batches} symbols: {batch}")

        # classify symbols
        new_syms      = [s for s in batch if s not in info or info[s][0] is None]
        recheck_syms  = [s for s in batch if s in info and info[s][1] is not None]
        use_group     = len(new_syms)==0

        # if groupable, download last‐10‐plus window once
        if use_group:
            start_dates = [info[s][1] for s in recheck_syms]
            window_start = min(start_dates)
            dl_kwargs = {
                "tickers":     [s.replace('.', '-').replace('$','-').upper() for s in batch],
                "start":       window_start.isoformat(),
                "end":         (datetime.now().date()+timedelta(days=1)).isoformat(),
                "interval":    "1d",
                "group_by":    "ticker",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logger.info(f"{table_name} batch {b+1}: group re‐download from {window_start}")
            for attempt in range(1, MAX_BATCH_RETRIES+1):
                log_mem(f"{table_name} batch {b+1} dl start")
                try:
                    df_group = yf.download(**dl_kwargs)
                    break
                except Exception as e:
                    logger.warning(f"group download failed: {e}; retrying…")
                    time.sleep(RETRY_DELAY)
            else:
                logger.error(f"group download aborted after {MAX_BATCH_RETRIES}")
                failed.extend(batch)
                continue
            log_mem(f"{table_name} after group download")

        rows = []
        symbol_row_counts = {}

        # 2) Process each symbol
        for sym in batch:
            last_date, earliest = info.get(sym, (None,None))
            yq = sym.replace('.', '-').replace('$','-').upper()

            # fetch data
            if sym in new_syms:
                logger.info(f"{sym}: new → full history download")
                try:
                    df = yf.download(
                        tickers=yq, period="max", interval="1d",
                        auto_adjust=True, actions=True,
                        threads=True, progress=False
                    )
                except Exception as e:
                    logger.warning(f"{sym} full download failed: {e}")
                    failed.append(sym)
                    symbol_row_counts[sym] = 0
                    continue
            else:
                # try group
                try:
                    # if multi‐ticker group
                    df = df_group[yq] if hasattr(df_group.columns, 'nlevels') else df_group
                except Exception:
                    logger.info(f"{sym}: missing in group → fallback full download")
                    try:
                        df = yf.download(
                            tickers=yq, period="max", interval="1d",
                            auto_adjust=True, actions=True,
                            threads=True, progress=False
                        )
                    except Exception as e:
                        logger.warning(f"{sym} fallback download failed: {e}")
                        failed.append(sym)
                        symbol_row_counts[sym] = 0
                        continue

            # validate
            if df is None or df.empty or "Open" not in df.columns:
                logger.warning(f"{sym}: no usable data; skipping")
                failed.append(sym)
                symbol_row_counts[sym] = 0
                continue

            log_mem(f"{sym} after download")

            # clean
            df = df.sort_index()
            df = df[df["Open"].notna()]

            # apply 10‐day recheck or current‐only slice
            if sym in recheck_syms:
                # slice the window
                df_window = df[df.index.date >= earliest]
                # detect missing business days
                expected = set(pd.bdate_range(earliest, datetime.now().date()).date)
                actual   = set(df_window.index.date)
                missing  = sorted(expected - actual)
                if missing:
                    logger.info(f"{sym}: missing dates {missing} → full reload")
                    try:
                        df_full = yf.download(
                            tickers=yq, period="max", interval="1d",
                            auto_adjust=True, actions=True,
                            threads=True, progress=False
                        )
                    except Exception as e:
                        logger.warning(f"{sym} full reload failed: {e}")
                        failed.append(sym)
                        symbol_row_counts[sym] = 0
                        continue
                    df = df_full.sort_index()
                    df = df[df["Open"].notna()]
                else:
                    df = df_window
            elif last_date:
                # only refresh current
                df = df[df.index.date >= last_date]
            # else new symbol → df stays full history

            count = len(df)
            symbol_row_counts[sym] = count
            if count == 0:
                logger.info(f"{sym}: no rows to upsert")
                continue

            logger.info(f"{sym}: {count} rows to upsert/update")
            for ts, row in df.iterrows():
                rows.append([
                    sym,
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

        # 3) Batch upsert
        if rows:
            upsert_sql = f"""
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
            execute_values(cur, upsert_sql, rows)
            conn.commit()
            inserted += len(rows)
            logger.info(f"{table_name} batch {b+1}/{batches}: upserted {len(rows)} rows")

        # 4) Batch summary
        succeeded = [s for s,c in symbol_row_counts.items() if c>0]
        skipped   = [s for s,c in symbol_row_counts.items() if c==0]
        logger.info(
            f"{table_name} batch {b+1}/{batches} summary – "
            f"succeeded ({len(succeeded)}): {succeeded}; "
            f"skipped ({len(skipped)}): {skipped}; "
            f"failed ({len(failed)}): {failed}"
        )

        # cleanup & pause
        if use_group:
            del df_group
        del rows
        gc.collect()
        log_mem(f"{table_name} batch {b+1} end")
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

    # Deduplicate old rows & create unique indexes
    logger.info("Deduplicating & indexing…")
    cur.execute(f"""
WITH r AS (
  SELECT ctid,
         ROW_NUMBER() OVER (PARTITION BY symbol, date ORDER BY ctid) AS rn
  FROM price_daily
)
DELETE FROM price_daily WHERE ctid IN (SELECT ctid FROM r WHERE rn>1);
CREATE UNIQUE INDEX IF NOT EXISTS price_daily_sym_date_idx
  ON price_daily(symbol, date);
""")
    cur.execute(f"""
WITH r AS (
  SELECT ctid,
         ROW_NUMBER() OVER (PARTITION BY symbol, date ORDER BY ctid) AS rn
  FROM etf_price_daily
)
DELETE FROM etf_price_daily WHERE ctid IN (SELECT ctid FROM r WHERE rn>1);
CREATE UNIQUE INDEX IF NOT EXISTS etf_price_daily_sym_date_idx
  ON etf_price_daily(symbol, date);
""")
    conn.commit()

    # Load stocks
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices_incremental("price_daily", stock_syms, cur, conn)

    # Load ETFs
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices_incremental("etf_price_daily", etf_syms, cur, conn)

    # Record run
    cur.execute("""
INSERT INTO last_updated (script_name, last_run)
VALUES (%s, NOW())
ON CONFLICT (script_name) DO UPDATE
  SET last_run = EXCLUDED.last_run;
""", (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logger.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logger.info(f"Stocks — total: {t_s}, upserted: {i_s}, failed: {len(f_s)}")
    logger.info(f"ETFs   — total: {t_e}, upserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logger.info("All done.")
