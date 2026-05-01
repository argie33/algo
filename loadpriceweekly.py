#!/usr/bin/env python3
# TRIGGER: 20260501_084523 - Phase 2: Weekly price data
# Weekly price data loader - fetches weekly OHLCV data for all symbols
# Triggered: 2026-04-28 14:40 UTC - AWS Batch 2 Parallel Execution (3 concurrent)
# Strategy: Incremental loading with incremental data append
import sys
import time
import logging
import json
import os
import gc
import math
import signal
import threading
import argparse
from datetime import timedelta
from collections import defaultdict

# Windows compatibility: resource module doesn't exist on Windows
try:
    import resource
    HAS_RESOURCE = True
except ImportError:
    HAS_RESOURCE = False

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from datetime import datetime

import boto3
import pandas as pd
import yfinance as yf

# ─── Timeout handler to forcibly kill hung downloads ───────────────
class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Download timed out - forcing kill")

def download_with_timeout(tickers, period="3mo", interval="1wk", timeout_seconds=90):
    """Wrapper that downloads with timeout protection using threading (cross-platform)"""
    result = {'df': None, 'error': None}

    def fetch_data():
        try:
            result['df'] = yf.download(
                tickers=tickers,
                period=period,
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                actions=True,
                threads=True,
                progress=False,
                timeout=60
            )
        except Exception as e:
            result['error'] = e

    thread = threading.Thread(target=fetch_data, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        raise TimeoutException(f"Download timeout after {timeout_seconds}s")

    if result['error']:
        raise result['error']

    return result['df']

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadpriceweekly.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    """Get RSS memory in MB, cross-platform."""
    if not HAS_RESOURCE:
        try:
            import psutil
            return psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            return 0
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry settings - improved for better network resilience
# -------------------------------
MAX_BATCH_RETRIES   = 3
RETRY_DELAY         = 0.2   # seconds between download retries
MAX_SYMBOL_RETRIES  = 12    # increased from 5 - more retries for timeout-prone symbols
RATE_LIMIT_BASE_DELAY = 120  # start with 120 seconds for rate limits
TIMEOUT_MAX_DELAY   = 120   # max seconds to wait for a single timeout retry

# -------------------------------
# Price-weekly columns
# -------------------------------
PRICE_COLUMNS = [
    "date","open","high","low","close",
    "adj_close","volume","dividends","stock_splits"
]
COL_LIST     = ", ".join(["symbol"] + PRICE_COLUMNS)

# -------------------------------
# DB config loader
# -------------------------------
def get_db_config():
    """Get database configuration from environment variables with fallbacks.

    Tries in order:
    1. AWS Secrets Manager (if AWS_REGION + DB_SECRET_ARN set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS Secrets Manager first if both vars are set
    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f" Using AWS Secrets Manager for credentials")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"  AWS Secrets Manager failed: {str(e)[:100]} - trying environment variables...")

    # Fallback to environment variables for local development
    db_host = os.environ.get("DB_HOST")
    db_user = os.environ.get("DB_USER")
    db_password = os.environ.get("DB_PASSWORD")
    db_name = os.environ.get("DB_NAME")
    db_port = os.environ.get("DB_PORT", "5432")

    if db_host and db_user and db_password and db_name:
        logging.info(f" Using environment variables for database connection")
        return {
            "host": db_host,
            "port": int(db_port),
            "user": db_user,
            "password": db_password,
            "dbname": db_name
        }

    raise EnvironmentError(
        " Cannot find database credentials. Provide either:\n"
        "  AWS: AWS_REGION + DB_SECRET_ARN\n"
        "  Local: DB_HOST + DB_USER + DB_PASSWORD + DB_NAME"
    )

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted, failed = 0, []
    timeout_failures = []  # Track timeouts separately for end-of-load retry
    CHUNK_SIZE, PAUSE = 5, 2.0  # MEMORY CONSERVATIVE MODE  # Single symbol, 0.5s pause - optimized for speed
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        yq_batch = [s.replace('.', '-').replace('$','-').upper() for s in batch]
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download full history ──────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = download_with_timeout(yq_batch, timeout_seconds=90)
                break
            except Exception as e:
                logging.warning(f"{table_name} download failed: {e}; retrying…")
                time.sleep(RETRY_DELAY)
        else:
            # Fallback: try downloading each symbol individually with retry logic
            logging.info(f"{table_name} batch {batch_idx+1} - attempting per-symbol download as fallback")
            per_symbol_results = {}
            for orig_sym in batch:
                symbol_success = False
                last_error = None
                for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                    try:
                        single_df = download_with_timeout([orig_sym], timeout_seconds=90)
                        if not single_df.empty:
                            per_symbol_results[orig_sym] = single_df
                            symbol_success = True
                            last_error = None
                            break
                        else:
                            logging.warning(f"{table_name} — {orig_sym}: no data (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                            last_error = "no_data"
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(1)
                    except Exception as e:
                        error_msg = str(e)
                        last_error = error_msg
                        # Calculate exponential backoff delay (2^attempt seconds, max TIMEOUT_MAX_DELAY)
                        exp_backoff_delay = min(2 ** (sym_attempt - 1), TIMEOUT_MAX_DELAY)

                        if "Too Many Requests" in error_msg or "Rate limit" in error_msg or "YFRateLimit" in str(type(e).__name__):
                            delay = RATE_LIMIT_BASE_DELAY
                            logging.warning(f"{table_name} — {orig_sym}: rate limited (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), waiting {delay}s")
                            time.sleep(delay)
                        elif "Timeout" in error_msg or "timed out" in error_msg.lower() or "connection" in error_msg.lower():
                            # Use exponential backoff for timeout errors
                            logging.warning(f"{table_name} — {orig_sym}: timeout (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), exponential backoff: {exp_backoff_delay}s")
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(exp_backoff_delay)
                        elif "Period" in error_msg and "invalid" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: invalid period - skipping")
                            break
                        elif "delisted" in error_msg or "no price data" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: delisted - skipping")
                            break
                        else:
                            logging.warning(f"{table_name} — {orig_sym}: error (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}): {e}")
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(exp_backoff_delay)
                if not symbol_success:
                    # Track timeout failures separately for end-of-load retry
                    if last_error and "Timeout" in str(last_error):
                        timeout_failures.append(orig_sym)
                    else:
                        failed.append(orig_sym)
            if per_symbol_results:
                df = per_symbol_results
            else:
                logging.error(f"{table_name} batch {batch_idx+1} failed completely - all symbols skipped")
                failed += batch
                continue

        log_mem(f"{table_name} after yf.download")
        cur.execute("SELECT 1;")   # ping DB

        # ─── Batch-insert per symbol ─────────────────────────────
        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                try:
                    sub = df[yq_sym] if len(yq_batch) > 1 else df
                except KeyError:
                    logging.warning(f"No data for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()

                # Flatten MultiIndex columns if needed
                if isinstance(sub.columns, pd.MultiIndex):
                    # Extract the data column (last level) and make lowercase
                    sub.columns = [col[-1].lower() for col in sub.columns]
                else:
                    # Regular columns - just lowercase
                    sub.columns = [str(col).lower() for col in sub.columns]

                if "open" not in sub.columns:
                    logging.warning(f"No 'open' column for {orig_sym} - columns: {list(sub.columns)}")
                    failed.append(orig_sym)
                    continue

                sub = sub[sub["open"].notna()]
                if sub.empty:
                    logging.warning(f"No valid price rows for {orig_sym}; skipping")
                    failed.append(orig_sym)
                    continue

                rows = []
                for idx, row in sub.iterrows():
                    try:
                        volume = None if math.isnan(row.get("volume", float("nan")))    else int(row.get("volume", 0))
                        # Skip records with zero or missing volume - these represent non-trading weeks or delisted stocks
                        if volume is None or volume == 0:
                            continue

                        rows.append([
                            orig_sym,
                            idx.date(),
                            None if math.isnan(row.get("open", float("nan")))      else float(row["open"]),
                            None if math.isnan(row.get("high", float("nan")))      else float(row["high"]),
                            None if math.isnan(row.get("low", float("nan")))       else float(row["low"]),
                            None if math.isnan(row.get("close", float("nan")))     else float(row["close"]),
                            None if math.isnan(row.get("adj close", row.get("close", float("nan")))) else float(row.get("adj close", row["close"])),
                            volume,
                            0.0  if ("dividends" not in row or (isinstance(row["dividends"], float) and math.isnan(row["dividends"]))) else (0.0 if not isinstance(row["dividends"], (int, float)) else float(row["dividends"])),
                            0.0  if ("stock splits" not in row or (isinstance(row["stock splits"], float) and math.isnan(row["stock splits"]))) else (0.0 if not isinstance(row["stock splits"], (int, float)) else float(row["stock splits"]))
                        ])
                    except (KeyError, ValueError, TypeError) as e:
                        logging.debug(f"{orig_sym} row parse error: {e}, skipping row")
                        continue

                if not rows:
                    logging.warning(f"{orig_sym}: no rows after cleaning; skipping")
                    failed.append(orig_sym)
                    continue

                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume, dividends = EXCLUDED.dividends, stock_splits = EXCLUDED.stock_splits"
                execute_values(cur, sql, rows)
                conn.commit()
                inserted += len(rows)
                logging.info(f"{table_name} — {orig_sym}: batch-inserted {len(rows)} rows")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)

    # ─── End-of-load retry for timeout failures ──────────────────────────────
    if timeout_failures:
        logging.info(f"{table_name} – retrying {len(timeout_failures)} timeout failures at end of load: {timeout_failures}")
        for orig_sym in timeout_failures:
            symbol_success = False
            for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                try:
                    single_df = yf.download(orig_sym, period="3mo", interval="1wk", auto_adjust=False, actions=True, progress=False, timeout=60)
                    if not single_df.empty:
                        # Now insert this data into database
                        rows = []
                        single_df = single_df.sort_index()
                        single_df = single_df[single_df["Open"].notna()]
                        for idx, row in single_df.iterrows():
                            rows.append([
                                orig_sym,
                                idx.date(),
                                None if math.isnan(row["Open"])      else float(row["Open"]),
                                None if math.isnan(row["High"])      else float(row["High"]),
                                None if math.isnan(row["Low"])       else float(row["Low"]),
                                None if math.isnan(row["Close"])     else float(row["Close"]),
                                None if math.isnan(row.get("Adj Close", row["Close"])) else float(row.get("Adj Close", row["Close"])),
                                None if math.isnan(row["Volume"])    else int(row["Volume"]),
                                0.0  if ("Dividends" not in row or math.isnan(row["Dividends"])) else float(row["Dividends"]),
                                0.0  if ("Stock Splits" not in row or math.isnan(row["Stock Splits"])) else float(row["Stock Splits"])
                            ])
                        if rows:
                            sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s"
                            execute_values(cur, sql, rows)
                            conn.commit()
                            inserted += len(rows)
                            logging.info(f"{table_name} — {orig_sym} (RETRY): batch-inserted {len(rows)} rows")
                            symbol_success = True
                            break
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: still no data on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(2)
                except Exception as e:
                    error_msg = str(e)
                    if "Timeout" in error_msg:
                        logging.warning(f"{table_name} — {orig_sym}: timeout on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        time.sleep(3)
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: error on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}): {e}")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(2)
            if not symbol_success:
                failed.append(orig_sym)
                logging.error(f"{table_name} — {orig_sym}: FAILED on retry - moving to failed list")

    return total, inserted, failed


def load_prices_smart(table_name, symbols, cur, conn):
    """
    FAST incremental loader: queries DB for max(date) per symbol, then
    downloads ONLY missing data. Batches 200 symbols at once via yf.download().
    For weekly data: ~25 API calls vs 1000+ for full reload.
    """
    from datetime import date

    logging.info(f"[SMART] {table_name}: loading {len(symbols)} symbols in smart incremental mode")
    start_wall = time.time()

    cur.execute(f"SELECT symbol, MAX(date) AS last_date FROM {table_name} WHERE symbol = ANY(%s) GROUP BY symbol", (symbols,))
    existing = {r["symbol"]: r["last_date"] for r in cur.fetchall()}
    logging.info(f"[SMART] {table_name}: {len(existing)} symbols already have data in DB")

    today = date.today()
    need_full = [s for s in symbols if s not in existing]
    need_incr = [s for s in symbols if s in existing and existing[s] < today]
    up_to_date = [s for s in symbols if s in existing and existing[s] >= today]
    logging.info(f"[SMART] {table_name}: need_full={len(need_full)}, need_incr={len(need_incr)}, up_to_date={len(up_to_date)}")

    total_inserted, total_failed = 0, []
    INCR_BATCH, FULL_BATCH = 200, 50
    INCR_PAUSE, FULL_PAUSE = 1.0, 2.0

    def _download_and_insert(batch_syms, start_date=None, period=None, pause=1.0):
        yq_batch = [s.replace('.', '-').replace('$', '-P') for s in batch_syms]
        mapping = dict(zip(yq_batch, batch_syms))
        n_ins, n_fail = 0, []

        for attempt in range(1, 4):
            try:
                kwargs = dict(tickers=yq_batch, interval="1wk", auto_adjust=False,
                              actions=True, threads=True, progress=False)
                if start_date:
                    kwargs["start"] = start_date.isoformat()
                else:
                    kwargs["period"] = period or "max"
                df = yf.download(**kwargs)
                break
            except Exception as e:
                logging.warning(f"[SMART] download attempt {attempt}/3 failed: {e}")
                time.sleep(2 ** attempt)
                df = None

        if df is None or (hasattr(df, 'empty') and df.empty):
            return 0, batch_syms

        gc.disable()
        try:
            for yq_sym, orig_sym in mapping.items():
                try:
                    if isinstance(df.columns, pd.MultiIndex):
                        if yq_sym not in df.columns.get_level_values(0):
                            continue
                        sub = df[yq_sym].copy()
                    else:
                        sub = df.copy()

                    sub.columns = [c.lower().replace(' ', '_') if isinstance(c, str) else str(c).lower() for c in sub.columns]
                    sub = sub.sort_index()
                    if "open" in sub.columns:
                        sub = sub[sub["open"].notna()]

                    rows = []
                    for idx, row in sub.iterrows():
                        try:
                            o = float(row.get("open", float("nan")))
                            h = float(row.get("high", float("nan")))
                            l = float(row.get("low", float("nan")))
                            c = float(row.get("close", float("nan")))
                            ac = float(row.get("adj_close", row.get("close", float("nan"))))
                            v = row.get("volume", None)
                            vol = None if v is None or (isinstance(v, float) and math.isnan(v)) else int(v)
                            if vol is None or vol == 0:
                                continue
                            div = float(row.get("dividends", 0.0) or 0.0)
                            sp = float(row.get("stock_splits", 0.0) or 0.0)
                            if any(math.isnan(x) for x in [o, h, l, c]):
                                continue
                            rows.append([orig_sym, idx.date(), o, h, l, c, ac, vol, div, sp])
                        except Exception:
                            continue

                    if rows:
                        sql = (f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s "
                               f"ON CONFLICT (symbol, date) DO UPDATE SET "
                               f"open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, "
                               f"close=EXCLUDED.close, adj_close=EXCLUDED.adj_close, "
                               f"volume=EXCLUDED.volume, dividends=EXCLUDED.dividends, "
                               f"stock_splits=EXCLUDED.stock_splits")
                        execute_values(cur, sql, rows)
                        conn.commit()
                        n_ins += len(rows)
                except Exception as e:
                    logging.warning(f"[SMART] {orig_sym} insert error: {e}")
                    n_fail.append(orig_sym)
                    conn.rollback()
        finally:
            gc.enable()

        time.sleep(pause)
        return n_ins, n_fail

    if need_incr:
        date_groups = defaultdict(list)
        for s in need_incr:
            date_groups[existing[s]].append(s)
        for last_date, group in sorted(date_groups.items()):
            start_date = last_date + timedelta(days=1)
            logging.info(f"[SMART] incremental: {len(group)} symbols from {start_date}")
            for i in range(0, len(group), INCR_BATCH):
                batch = group[i:i+INCR_BATCH]
                ins, fail = _download_and_insert(batch, start_date=start_date, pause=INCR_PAUSE)
                total_inserted += ins
                total_failed.extend(fail)
                logging.info(f"[SMART] incr batch {i//INCR_BATCH+1}: inserted {ins} rows, {len(fail)} failed")

    if need_full:
        logging.info(f"[SMART] full history: {len(need_full)} symbols")
        for i in range(0, len(need_full), FULL_BATCH):
            batch = need_full[i:i+FULL_BATCH]
            ins, fail = _download_and_insert(batch, period="max", pause=FULL_PAUSE)
            total_inserted += ins
            total_failed.extend(fail)
            logging.info(f"[SMART] full batch {i//FULL_BATCH+1}/{(len(need_full)+FULL_BATCH-1)//FULL_BATCH}: inserted {ins} rows")

    elapsed = time.time() - start_wall
    logging.info(f"[SMART] {table_name}: DONE in {elapsed:.1f}s — inserted {total_inserted} rows, {len(total_failed)} failed")
    return len(symbols), total_inserted, total_failed


# -------------------------------
# Entrypoint
# -------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Load weekly price data for stocks')
    parser.add_argument('--smart', action='store_true',
                       help='Smart incremental: only fetch missing data per symbol. FAST (5-10 min vs hours).')
    args = parser.parse_args()

    if args.smart:
        logging.info("Running in SMART mode - incremental per-symbol fetch")
    else:
        logging.info("Running in DEFAULT mode - loading recent 3 months of data")

    try:
        log_mem("startup")
        logging.info("Starting priceweekly loader...")

        # Connect to DB with timeout
        cfg  = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"],
            connect_timeout=30,
            options='-c statement_timeout=600000'
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Create table if it doesn't exist (preserve existing data)
        try:
            logging.info("Ensuring price_weekly table exists…")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS price_weekly (
                    id           SERIAL PRIMARY KEY,
                    symbol       VARCHAR(10) NOT NULL,
                    date         DATE         NOT NULL,
                    open         DOUBLE PRECISION,
                    high         DOUBLE PRECISION,
                    low          DOUBLE PRECISION,
                    close        DOUBLE PRECISION,
                    adj_close    DOUBLE PRECISION,
                    volume       BIGINT,
                    dividends    DOUBLE PRECISION,
                    stock_splits DOUBLE PRECISION,
                    fetched_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_price_weekly_symbol ON price_weekly(symbol);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_price_weekly_symbol_date ON price_weekly(symbol, date);")
            logging.info(" price_weekly table ready")
            conn.commit()
        except Exception as e:
            logging.error(f" Failed to create price_weekly table: {e}")
            conn.rollback()
            raise

        # Load stock symbols only (ETF tables are managed by loadetfpriceweekly.py)
        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        if args.smart:
            t_s, i_s, f_s = load_prices_smart("price_weekly", stock_syms, cur, conn)
        else:
            t_s, i_s, f_s = load_prices("price_weekly", stock_syms, cur, conn)

        t_w, i_w, f_w = 0, 0, []  # ETFs handled by separate loader

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
        logging.info(f"Stocks      — total: {t_s}, inserted: {i_s}, failed: {len(f_s)}")
        logging.info(f"ETFs        — total: {t_w}, inserted: {i_w}, failed: {len(f_w)}")

        cur.close()
        conn.close()
        logging.info("All done. Exiting successfully.")
        sys.exit(0)
        
    except KeyError as e:
        logging.error(f"Missing environment variable: {e}")
        sys.exit(1)
    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)
