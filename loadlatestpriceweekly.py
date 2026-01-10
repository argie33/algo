#!/usr/bin/env python3
# Latest weekly price data loader - fetches current week OHLCV data
# Trigger deploy-app-stocks workflow test - latest weekly loader v5 - enhanced error handling and robustness
import sys
import time
import logging
import json
import os
import gc
import resource
import pandas as pd
from dotenv import load_dotenv

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime, timedelta

import boto3
import yfinance as yf
from db_helper import get_db_connection

# Load environment from .env.local
load_dotenv('/home/stocks/algo/.env.local')

# -------------------------------
# Script metadata & logging setup 
# -------------------------------
SCRIPT_NAME = "loadlatestpriceweekly.py"
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
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)

def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

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
    """Get database configuration from AWS Secrets Manager or local environment.
    
    AWS Production: Requires DB_SECRET_ARN environment variable (Lambda/ECS)
    Local Development: Uses DB_HOST, DB_USER, DB_PASSWORD, DB_NAME environment variables
    Defaults: localhost:5432 (postgres/password)
    """
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        # Fall back to local database configuration (development/local testing)
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }
def extract_scalar(val):
    """
    If pandas gives us a one-element Series, pull out that element.
    Otherwise, return val as-is.
    """
    if isinstance(val, pd.Series) and len(val) == 1:
        return val.iloc[0]
    return val

def get_week_boundaries(date):
    """Get start and end of the week containing the given date"""
    # Monday is 0 and Sunday is 6
    start = date - timedelta(days=date.weekday())
    end = start + timedelta(days=6)
    return start, end

# -------------------------------
# Incremental loader (always refresh last week and current week)
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
        res       = cur.fetchone()
        last_date = (res["last_date"] if isinstance(res, dict) else res[0])
        today     = datetime.now().date()

        if last_date:
            # Get current and previous week boundaries
            current_week_start, _ = get_week_boundaries(today)
            last_week_start = current_week_start - timedelta(days=7)
            
            # Start from previous week start
            start_date = last_week_start
            
            download_kwargs = {
                "tickers":     yq_sym,
                "start":       start_date.isoformat(),
                "end":         (today + timedelta(days=1)).isoformat(),
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

        # ─── Clean and prepare rows ─────────────────────────────
        df = df.sort_index()
        if "Open" not in df.columns:
            logging.warning(f"{table_name} – {orig_sym}: unexpected data format; skipping")
            failed.append(orig_sym)
            continue

        df = df[df["Open"].notna()]
        rows = []
        for idx, row in df.iterrows():
            o  = extract_scalar(row["Open"])
            h  = extract_scalar(row["High"])
            l  = extract_scalar(row["Low"])
            c  = extract_scalar(row["Close"])
            ac = extract_scalar(row.get("Adj Close", c))
            v  = extract_scalar(row["Volume"])
            d  = extract_scalar(row.get("Dividends", 0.0))
            s  = extract_scalar(row.get("Stock Splits", 0.0))

            rows.append([
                orig_sym,
                idx.date(),
                None if pd.isna(o)  else float(o),
                None if pd.isna(h)  else float(h),
                None if pd.isna(l)  else float(l),
                None if pd.isna(c)  else float(c),
                None if pd.isna(ac) else float(ac),
                None if pd.isna(v)  else int(v),
                0.0  if pd.isna(d)  else float(d),
                0.0  if pd.isna(s)  else float(s)
            ])

        if not rows:
            logging.warning(f"{table_name} – {orig_sym}: no valid rows after cleaning; skipping")
            failed.append(orig_sym)
            continue

        # ─── Insert into DB ─────────────────────────────────────
        sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
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
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"]
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