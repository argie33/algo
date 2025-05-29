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
SCRIPT_NAME = "loadpriceweekly.py"
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
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB")

# -------------------------------
# Retry settings
# -------------------------------
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2  # seconds between download retries

# -------------------------------
# Price-weekly columns
# -------------------------------
PRICE_COLUMNS = [
    "date", "open", "high", "low", "close",
    "adj_close", "volume", "dividends", "stock_splits"
]
COL_LIST = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Load database configuration from AWS Secrets Manager."""
    session = boto3.session.Session()
    client  = session.client(service_name="secretsmanager")
    secret  = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    config  = json.loads(secret["SecretString"])
    return (
        config["username"],
        config["password"],
        config["host"],
        config["port"],
        config["dbname"]
    )

# -------------------------------
# Helper to extract a single scalar
# -------------------------------
def extract_scalar(val):
    """Convert a scalar value to the appropriate type."""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not math.isnan(val) else None
    return val

# -------------------------------
# Incremental loader (always refresh current bar)
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    logging.info(f"Loading {table_name}: {len(symbols)} symbols")
    inserted = 0
    failed   = []

    for orig_sym in symbols:
        yq_sym = orig_sym.replace('.', '-').replace('$', '-').upper()

        # ─── Determine starting point ───────────────────────────
        cur.execute(
            f"SELECT MAX(date) AS last_date FROM {table_name} WHERE symbol = %s;",
            (orig_sym,)
        )
        res = cur.fetchone()
        last_date = (res["last_date"] if isinstance(res, dict) else res[0])
        today     = datetime.now().date()

        if last_date:
            # For weekly data, get last 2 weeks
            two_weeks_ago = today - timedelta(days=14)
            start_date = two_weeks_ago
            
            # Delete existing records for these specific dates
            cur.execute(
                f"DELETE FROM {table_name} WHERE symbol = %s AND date >= %s AND date <= %s;",
                (orig_sym, start_date, today)
            )
            conn.commit()
            
            download_kwargs = {
                "tickers":     yq_sym,
                "start":       start_date.isoformat(),
                "end":        (today + timedelta(days=1)).isoformat(),
                "interval":    "1wk",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logging.info(f"{table_name} – {orig_sym}: downloading from {start_date} to {today}")
        else:
            download_kwargs = {
                "tickers":     yq_sym,
                "period":      "max",
                "interval":    "1wk",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logging.info(f"{table_name} – {orig_sym}: no existing data; downloading full history")

        # ─── Download with retries ───────────────────────────────
        df = None
        for attempt in range(1, MAX_BATCH_RETRIES + 1):
            try:
                logging.info(f"{table_name} – {orig_sym}: download attempt {attempt}")
                log_mem(f"{table_name} {orig_sym} download start")
                df = yf.download(**download_kwargs)
                break
            except Exception as e:
                logging.warning(f"{table_name} – {orig_sym}: download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)

        if df is None or df.empty:
            logging.warning(f"{table_name} – {orig_sym}: no data returned; skipping")
            failed.append(orig_sym)
            continue

        df = df[df["Open"].notna()]
        rows = []
        
        # Get the actual date range from downloaded data and delete those dates
        dates = [idx.date() for idx in df.index]
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            cur.execute(
                f"DELETE FROM {table_name} WHERE symbol = %s AND date >= %s AND date <= %s;",
                (orig_sym, min_date, max_date)
            )
            conn.commit()
            
        for idx, row in df.iterrows():
            o  = extract_scalar(row["Open"])
            h  = extract_scalar(row["High"])
            l  = extract_scalar(row["Low"])
            c  = extract_scalar(row["Close"])
            ac = extract_scalar(row.get("Adj Close", c))
            v  = extract_scalar(row["Volume"])
            d  = extract_scalar(row.get("Dividends", 0.0))
            s  = extract_scalar(row.get("Stock Splits", 0.0))
            
            if not any(x is not None for x in (o, h, l, c, v)):
                continue
                
            rows.append([
                orig_sym,
                idx.date(),
                o, h, l, c, ac, v, d, s
            ])

        if not rows:
            logging.warning(f"{table_name} – {orig_sym}: no valid rows; skipping")
            failed.append(orig_sym)
            continue

        # ─── Insert all rows at once ──────────────────────────────
        sql = f"""
        INSERT INTO {table_name} (
            symbol, date, open, high, low, close,
            adj_close, volume, dividends, stock_splits
        ) VALUES %s;
        """
        execute_values(cur, sql, rows)
        conn.commit()
        inserted += len(rows)
        logging.info(f"{table_name} – {orig_sym}: inserted {len(rows)} rows")
        log_mem(f"{table_name} {orig_sym} insert end")

        time.sleep(0.1)

    return len(symbols), inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    log_mem("startup")

    # Connect to DB
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg[2], port=cfg[3],
        user=cfg[0], password=cfg[1],
        dbname=cfg[4]
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Load stock symbols incrementally
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_weekly", stock_syms, cur, conn)

    # Load ETF symbols incrementally
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_weekly", etf_syms, cur, conn)

    # Record last run
    cur.execute("""
      INSERT INTO last_updated (script_name, last_run)
      VALUES (%s, NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()

    peak = get_rss_mb()
    logging.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logging.info(f"Stocks — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, inserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.")