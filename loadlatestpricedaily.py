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
MAX_BATCH_RETRIES = 3
RETRY_DELAY       = 0.2  # seconds between download retries

# -------------------------------
# Price-daily columns
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
# Helper to extract a single scalar
# -------------------------------
def extract_scalar(val):
    """
    If pandas gives us a one-element Series, pull out that element.
    Otherwise, return val as-is.
    """
    if isinstance(val, pd.Series) and len(val) == 1:
        return val.iloc[0]
    return val

# -------------------------------
# Incremental loader (with backfill + upsert)
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    logging.info(f"Loading {table_name}: {len(symbols)} symbols")
    inserted = 0
    failed   = []

    for orig_sym in symbols:
        yq_sym = orig_sym.replace('.', '-').replace('$', '-').upper()

        # ─── Determine date bounds ────────────────────────────
        cur.execute(
            f"SELECT MIN(date) AS first_date, MAX(date) AS last_date "
            f"FROM {table_name} WHERE symbol = %s;",
            (orig_sym,)
        )
        res = cur.fetchone()
        first_date = (res["first_date"] if isinstance(res, dict) else res[0])
        last_date  = (res["last_date"]  if isinstance(res, dict) else res[1])
        today      = datetime.now().date()

        # ─── Backfill any historical gaps ─────────────────────
        if first_date:
            expected_dates = pd.bdate_range(start=first_date, end=last_date).date
            cur.execute(
                f"SELECT date FROM {table_name} "
                f"WHERE symbol = %s AND date BETWEEN %s AND %s;",
                (orig_sym, first_date, last_date)
            )
            existing = {r["date"] for r in cur.fetchall()}
            missing_dates = [d for d in expected_dates if d not in existing]

            if missing_dates:
                logging.info(f"{table_name} – {orig_sym}: found {len(missing_dates)} missing dates; backfilling")
                for md in missing_dates:
                    download_kwargs = {
                        "tickers":     yq_sym,
                        "start":       md.isoformat(),
                        "end":         (md + timedelta(days=1)).isoformat(),
                        "interval":    "1d",
                        "auto_adjust": True,
                        "actions":     True,
                        "threads":     True,
                        "progress":    False
                    }
                    logging.info(f"{table_name} – {orig_sym}: backfilling {md}")
                    df_md = None
                    for attempt in range(1, MAX_BATCH_RETRIES + 1):
                        try:
                            log_mem(f"{table_name} {orig_sym} backfill download start {md}")
                            df_md = yf.download(**download_kwargs)
                            break
                        except Exception as e:
                            logging.warning(f"{table_name} – {orig_sym}: backfill download failed ({e}); retrying…")
                            time.sleep(RETRY_DELAY)
                    if df_md is None or df_md.empty or "Open" not in df_md.columns:
                        logging.warning(f"{table_name} – {orig_sym}: backfill for {md} no data; skipping")
                        continue

                    df_md = df_md.sort_index()
                    df_md = df_md[df_md["Open"].notna()]

                    rows_md = []
                    for idx, row in df_md.iterrows():
                        o  = extract_scalar(row["Open"])
                        h  = extract_scalar(row["High"])
                        l  = extract_scalar(row["Low"])
                        c  = extract_scalar(row["Close"])
                        ac = extract_scalar(row.get("Adj Close", c))
                        v  = extract_scalar(row["Volume"])
                        d  = extract_scalar(row.get("Dividends", 0.0))
                        s  = extract_scalar(row.get("Stock Splits", 0.0))

                        rows_md.append([
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

                    if not rows_md:
                        logging.warning(f"{table_name} – {orig_sym}: no valid backfill rows for {md}; skipping")
                    else:
                        # Upsert missing rows
                        sql_upsert = f"""INSERT INTO {table_name} ({COL_LIST}) VALUES %s
                                         ON CONFLICT (symbol, date) DO UPDATE SET
                                           open         = EXCLUDED.open,
                                           high         = EXCLUDED.high,
                                           low          = EXCLUDED.low,
                                           close        = EXCLUDED.close,
                                           adj_close    = EXCLUDED.adj_close,
                                           volume       = EXCLUDED.volume,
                                           dividends    = EXCLUDED.dividends,
                                           stock_splits = EXCLUDED.stock_splits;"""
                        execute_values(cur, sql_upsert, rows_md)
                        conn.commit()
                        logging.info(f"{table_name} – {orig_sym}: backfilled {len(rows_md)} rows for {md}")
                        log_mem(f"{table_name} {orig_sym} backfill insert end {md}")

        # ─── Incremental / refresh previous & current bar ──────
        if last_date:
            download_kwargs = {
                "tickers":     yq_sym,
                "start":       last_date.isoformat(),
                "end":         (today + timedelta(days=1)).isoformat(),
                "interval":    "1d",
                "auto_adjust": True,
                "actions":     True,
                "threads":     True,
                "progress":    False
            }
            logging.info(f"{table_name} – {orig_sym}: downloading from {last_date} to {today}")
        else:
            download_kwargs = {
                "tickers":     yq_sym,
                "period":      "max",
                "interval":    "1d",
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

        # ─── Upsert into DB ────────────────────────────────────
        sql_upsert = f"""INSERT INTO {table_name} ({COL_LIST}) VALUES %s
                         ON CONFLICT (symbol, date) DO UPDATE SET
                           open         = EXCLUDED.open,
                           high         = EXCLUDED.high,
                           low          = EXCLUDED.low,
                           close        = EXCLUDED.close,
                           adj_close    = EXCLUDED.adj_close,
                           volume       = EXCLUDED.volume,
                           dividends    = EXCLUDED.dividends,
                           stock_splits = EXCLUDED.stock_splits;"""
        execute_values(cur, sql_upsert, rows)
        conn.commit()
        inserted += len(rows)
        logging.info(f"{table_name} – {orig_sym}: upserted {len(rows)} rows")
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

    # ─── Ensure unique index on (symbol,date) so ON CONFLICT works ───
    cur.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS price_daily_symbol_date_idx
      ON price_daily(symbol, date);
    """)
    cur.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS etf_price_daily_symbol_date_idx
      ON etf_price_daily(symbol, date);
    """)
    conn.commit()

    # Load stock symbols incrementally (with backfill & upsert)
    cur.execute("SELECT symbol FROM stock_symbols;")
    stock_syms = [r["symbol"] for r in cur.fetchall()]
    t_s, i_s, f_s = load_prices("price_daily", stock_syms, cur, conn)

    # Load ETF symbols incrementally (with backfill & upsert)
    cur.execute("SELECT symbol FROM etf_symbols;")
    etf_syms = [r["symbol"] for r in cur.fetchall()]
    t_e, i_e, f_e = load_prices("etf_price_daily", etf_syms, cur, conn)

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
    logging.info(f"Stocks — total: {t_s}, upserted: {i_s}, failed: {len(f_s)}")
    logging.info(f"ETFs   — total: {t_e}, upserted: {i_e}, failed: {len(f_e)}")

    cur.close()
    conn.close()
    logging.info("All done.")
