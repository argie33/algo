# URGENT REBUILD: 2026-01-28 03:15 UTC - AWS ECS Deployment Trigger - FORCE RUN TASKS
# ============================================================================
#!/usr/bin/env python3
# Daily price data loader - fetches OHLCV data for all symbols
# CRITICAL: Populates price_daily table with OHLCV data for all 5000+ symbols
# Required by: volatility calculations, technical indicators, momentum metrics
# Trigger: 2026-01-28 03:15 - Deploy to AWS ECS with all task definitions - NOW RUNNING TASKS
# Updated: 2026-01-28 - CloudFormation stack updated with new task definitions
import sys
import time
import logging
import json
import os
import gc
import math
import argparse
from pathlib import Path

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
from dotenv import load_dotenv

# Load environment variables from .env.local if it exists
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

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


def filter_symbols_by_range(symbols, symbol_range):
    """
    Filter symbols by range for parallel processing.
    Range examples: "A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF"
    """
    if not symbol_range or symbol_range is None:
        return symbols

    if symbol_range == "ETF":
        # Already filtered to ETFs by the caller
        return symbols

    # Parse range like "A-L" -> start='A', end='L'
    if '-' in symbol_range:
        start, end = symbol_range.split('-')
    else:
        start = end = symbol_range

    # Filter: symbol >= start AND symbol < chr(ord(end)+1)
    filtered = [s for s in symbols if start <= s[0] <= end]
    return filtered

# -------------------------------
# Retry settings - improved for better network resilience
# -------------------------------
MAX_BATCH_RETRIES   = 3
RETRY_DELAY         = 0.5   # seconds between download retries
MAX_SYMBOL_RETRIES  = 12    # increased from 8 - more retries for timeout-prone symbols
RATE_LIMIT_BASE_DELAY = 120  # start with 120 seconds when rate limited (yfinance is aggressive)
TIMEOUT_RETRY_DELAY = 30    # extra delay when retrying timeout failures at end-of-load (increased from 10)
TIMEOUT_MAX_DELAY   = 120   # max seconds to wait for a single timeout retry

# -------------------------------
# Price-daily columns
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
    """Get database configuration - supports both AWS Secrets Manager and local environment variables.

    Priority:
    1. AWS Secrets Manager (if AWS_REGION and DB_SECRET_ARN are set)
    2. Environment variables (DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT)
    """
    aws_region = os.environ.get("AWS_REGION")
    db_secret_arn = os.environ.get("DB_SECRET_ARN")

    # Try AWS first
    if aws_region and db_secret_arn:
        try:
            secret_str = boto3.client("secretsmanager", region_name=aws_region).get_secret_value(
                SecretId=db_secret_arn
            )["SecretString"]
            sec = json.loads(secret_str)
            logging.info(f" Loaded database credentials from AWS Secrets Manager: {db_secret_arn}")
            return {
                "host": sec["host"],
                "port": int(sec.get("port", 5432)),
                "user": sec["username"],
                "password": sec["password"],
                "dbname": sec["dbname"]
            }
        except Exception as e:
            logging.warning(f"AWS Secrets Manager failed ({e.__class__.__name__}): {str(e)[:100]}. Falling back to environment variables.")

    # Fall back to environment variables for local development
    logging.info(" Using environment variables for database config")
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "stocks"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "dbname": os.environ.get("DB_NAME", "stocks")
    }

# -------------------------------
# Main loader with batched inserts
# -------------------------------
def load_prices(table_name, symbols, cur, conn):
    total = len(symbols)
    logging.info(f"Loading {table_name}: {total} symbols")
    inserted, failed = 0, []
    timeout_failures = []  # Track timeouts separately for end-of-load retry
    CHUNK_SIZE, PAUSE = 5, 2.0   # 5 symbols per batch, 2.0s pause - MEMORY CONSERVATIVE MODE (prevent system crashes)
    batches = (total + CHUNK_SIZE - 1) // CHUNK_SIZE

    # Skip if no symbols to load
    if total == 0:
        logging.info(f"No symbols to load for {table_name}")
        return 0, 0, []

    for batch_idx in range(batches):
        batch    = symbols[batch_idx*CHUNK_SIZE:(batch_idx+1)*CHUNK_SIZE]
        # Handle preferred shares (symbols with $): use base ticker for yfinance
        yq_batch = []
        for s in batch:
            if '$' in s:
                # CADE$A -> CADE (use base ticker for preferred shares)
                base_ticker = s.split('$')[0]
                yq_batch.append(base_ticker)
            else:
                # Normal ticker conversion
                yq_batch.append(s.replace('.', '-').upper())
        mapping  = dict(zip(yq_batch, batch))

        # ─── Download full history ──────────────────────────────
        for attempt in range(1, MAX_BATCH_RETRIES+1):
            logging.info(f"{table_name} – batch {batch_idx+1}/{batches}, download attempt {attempt}")
            log_mem(f"{table_name} batch {batch_idx+1} start")
            try:
                df = yf.download(
                    tickers=yq_batch,
                    period=DATA_PERIOD,
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,    # preserved
                    actions=True,        # preserved
                    threads=True,        # preserved
                    progress=False       # preserved
                )
                logging.info(f"Downloaded dataframe for {yq_batch}: {df.shape if hasattr(df, 'shape') else type(df)}")
                break
            except Exception as e:
                logging.warning(f"{table_name} download failed (attempt {attempt}/{MAX_BATCH_RETRIES}): {e}")
                time.sleep(RETRY_DELAY)
                if attempt == MAX_BATCH_RETRIES:
                    logging.warning(f"{table_name} batch {batch_idx+1} failed all attempts - will retry per-symbol")
                    df = None
        else:
            df = None

        if df is None:
            # Fallback: try downloading each symbol individually with retry logic
            logging.info(f"{table_name} batch {batch_idx+1} - attempting per-symbol download as fallback")
            per_symbol_results = {}
            for orig_sym in batch:
                symbol_success = False
                last_error = None
                for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                    try:
                        single_df = yf.download(orig_sym, period=DATA_PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False)
                        if not single_df.empty:
                            # CRITICAL FIX: Normalize column names to lowercase (yfinance returns uppercase)
                            single_df.columns = [col.lower() if col is not None else "unknown" for col in single_df.columns]
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

                        # Check if it's a rate limit error
                        if "Too Many Requests" in error_msg or "Rate limit" in error_msg or "YFRateLimit" in str(type(e).__name__):
                            # Use aggressive delay for rate limits
                            delay = RATE_LIMIT_BASE_DELAY
                            logging.warning(f"{table_name} — {orig_sym}: rate limited (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), waiting {delay}s")
                            time.sleep(delay)
                        elif "Timeout" in error_msg or "timed out" in error_msg.lower() or "connection" in error_msg.lower():
                            # Use exponential backoff for timeout errors (longer delays for retry)
                            logging.warning(f"{table_name} — {orig_sym}: timeout (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}), exponential backoff: {exp_backoff_delay}s")
                            if sym_attempt < MAX_SYMBOL_RETRIES:
                                time.sleep(exp_backoff_delay)
                        elif "Period" in error_msg and "invalid" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: invalid period (test symbol) - skipping")
                            break
                        elif "delisted" in error_msg or "no price data" in error_msg:
                            logging.error(f"{table_name} — {orig_sym}: delisted/no data - skipping")
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
                    # Handle both single and multi-ticker dataframes
                    # When CHUNK_SIZE=1, even single downloads have MultiIndex columns from yfinance
                    if isinstance(df.columns, pd.MultiIndex):
                        # MultiIndex columns - extract the data for this symbol
                        if yq_sym in df.columns.get_level_values(0):
                            sub = df[yq_sym]
                        else:
                            logging.warning(f"No data for {orig_sym}; skipping")
                            failed.append(orig_sym)
                            continue
                    else:
                        # Flat columns - this is a single symbol download
                        sub = df
                except (KeyError, AttributeError) as e:
                    logging.warning(f"No data for {orig_sym}: {e}; skipping")
                    failed.append(orig_sym)
                    continue

                sub = sub.sort_index()
                # CRITICAL FIX: Normalize ALL column names to lowercase (yfinance returns UPPERCASE)
                # Flatten any remaining MultiIndex structure and lowercase
                try:
                    if isinstance(sub.columns, pd.MultiIndex):
                        # Extract the rightmost level of the MultiIndex
                        safe_cols = []
                        for col in sub.columns:
                            try:
                                if col is not None and isinstance(col, tuple) and len(col) > 0:
                                    safe_cols.append(str(col[-1]).lower())
                                elif col is not None:
                                    safe_cols.append(str(col).lower())
                                else:
                                    safe_cols.append("unknown")
                            except (TypeError, IndexError):
                                safe_cols.append("unknown")
                        sub.columns = safe_cols
                    else:
                        # Regular columns - just lowercase them
                        safe_cols = []
                        for col in sub.columns:
                            try:
                                if col is not None:
                                    safe_cols.append(str(col).lower())
                                else:
                                    safe_cols.append("unknown")
                            except (TypeError, AttributeError):
                                safe_cols.append("unknown")
                        sub.columns = safe_cols
                except Exception as e:
                    logging.warning(f"Error normalizing columns for {orig_sym}: {str(e)}, skipping")
                    continue

                # Verify that 'open' column exists after normalization
                if "open" not in sub.columns:
                    logging.warning(f"No 'open' column found for {orig_sym}; available columns: {list(sub.columns)}; skipping")
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
                        # Skip records with zero or missing volume - these represent non-trading days or delisted stocks
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
                            0.0  if ("dividends" not in row or math.isnan(row.get("dividends", float("nan")))) else float(row["dividends"]),
                            0.0  if ("stock splits" not in row or math.isnan(row.get("stock splits", float("nan")))) else float(row["stock splits"])
                        ])
                    except (KeyError, ValueError, TypeError) as e:
                        logging.debug(f"{orig_sym} row parse error: {e}, skipping row")
                        continue

                if not rows:
                    logging.warning(f"{orig_sym}: no rows after cleaning; skipping")
                    failed.append(orig_sym)
                    continue

                sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume, dividends = EXCLUDED.dividends, stock_splits = EXCLUDED.stock_splits"
                try:
                    execute_values(cur, sql, rows)
                    conn.commit()
                    inserted += len(rows)
                    logging.info(f"{table_name} — {orig_sym}: batch-inserted {len(rows)} rows")
                except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                    logging.error(f"{table_name} — {orig_sym}: database error during insert: {e}")
                    conn.rollback()
                    failed.append(orig_sym)
                    continue
            if inserted == 0:
                logging.warning(f"{table_name}: No rows inserted for batch {batch_idx+1}")
        finally:
            gc.enable()

        del df, batch, yq_batch, mapping
        gc.collect()
        log_mem(f"{table_name} batch {batch_idx+1} end")
        time.sleep(PAUSE)
        # Force additional garbage collection to prevent memory buildup
        gc.collect()

    # ─── End-of-load retry for timeout failures ──────────────────────────────
    if timeout_failures:
        logging.info(f"{table_name} – retrying {len(timeout_failures)} timeout failures at end of load: {timeout_failures}")
        for orig_sym in timeout_failures:
            symbol_success = False
            for sym_attempt in range(1, MAX_SYMBOL_RETRIES + 1):
                try:
                    single_df = yf.download(orig_sym, period=DATA_PERIOD, interval="1d", auto_adjust=False, actions=True, progress=False)
                    if not single_df.empty:
                        # Normalize column names to lowercase
                        single_df.columns = [col.lower() if col is not None else "unknown" for col in single_df.columns]
                        # Now insert this data into database
                        rows = []
                        single_df = single_df.sort_index()
                        single_df = single_df[single_df["open"].notna()]
                        for idx, row in single_df.iterrows():
                            rows.append([
                                orig_sym,
                                idx.date(),
                                None if math.isnan(row["open"])      else float(row["open"]),
                                None if math.isnan(row["high"])      else float(row["high"]),
                                None if math.isnan(row["low"])       else float(row["low"]),
                                None if math.isnan(row["close"])     else float(row["close"]),
                                None if math.isnan(row.get("adj close", row["close"])) else float(row.get("adj close", row["close"])),
                                None if math.isnan(row["volume"])    else int(row["volume"]),
                                0.0  if ("dividends" not in row or math.isnan(row["dividends"])) else float(row["dividends"]),
                                0.0  if ("stock splits" not in row or math.isnan(row["stock splits"])) else float(row["stock splits"])
                            ])
                        if rows:
                            sql = f"INSERT INTO {table_name} ({COL_LIST}) VALUES %s ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, close = EXCLUDED.close, adj_close = EXCLUDED.adj_close, volume = EXCLUDED.volume, dividends = EXCLUDED.dividends, stock_splits = EXCLUDED.stock_splits"
                            try:
                                execute_values(cur, sql, rows)
                                conn.commit()
                                inserted += len(rows)
                                logging.info(f"{table_name} — {orig_sym} (RETRY): batch-inserted {len(rows)} rows")
                                symbol_success = True
                                break
                            except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
                                logging.error(f"{table_name} — {orig_sym} (RETRY): database error during insert: {e}")
                                conn.rollback()
                                # Will retry on next attempt or mark as failed
                                continue
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: still no data on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(TIMEOUT_RETRY_DELAY)  # Use longer delay for timeout retries (10s)
                except Exception as e:
                    error_msg = str(e)
                    if "Timeout" in error_msg:
                        logging.warning(f"{table_name} — {orig_sym}: timeout on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES})")
                        time.sleep(TIMEOUT_RETRY_DELAY)  # Use longer delay for timeout (10s)
                    else:
                        logging.warning(f"{table_name} — {orig_sym}: error on retry (attempt {sym_attempt}/{MAX_SYMBOL_RETRIES}): {e}")
                        if sym_attempt < MAX_SYMBOL_RETRIES:
                            time.sleep(TIMEOUT_RETRY_DELAY)
            if not symbol_success:
                failed.append(orig_sym)
                logging.error(f"{table_name} — {orig_sym}: FAILED on retry - moving to failed list")

    return total, inserted, failed

# -------------------------------
# Entrypoint
# -------------------------------
def load_prices_smart(table_name, symbols, cur, conn):
    """
    FAST incremental loader: queries DB for max(date) per symbol, then
    downloads ONLY missing data. Batches 200 symbols at once via yf.download().

    - First run (no DB data): falls back to full history load for those symbols
    - Subsequent runs: downloads only 1-5 days of new data per batch
    - 5000 symbols: ~25 API calls instead of 1000 → 5-10 min vs 3-4 hours
    """
    from datetime import date, timedelta

    logging.info(f"[SMART] {table_name}: loading {len(symbols)} symbols in smart incremental mode")
    start_wall = time.time()

    # Step 1: Get max date already in DB for each symbol (single query)
    cur.execute(f"SELECT symbol, MAX(date) AS last_date FROM {table_name} WHERE symbol = ANY(%s) GROUP BY symbol", (symbols,))
    existing = {r["symbol"]: r["last_date"] for r in cur.fetchall()}
    logging.info(f"[SMART] {table_name}: {len(existing)} symbols already have data in DB")

    # Step 2: Separate symbols needing full history vs incremental update
    today = date.today()
    need_full = [s for s in symbols if s not in existing]
    need_incr = [s for s in symbols if s in existing and existing[s] < today]
    up_to_date = [s for s in symbols if s in existing and existing[s] >= today]

    logging.info(f"[SMART] {table_name}: need_full={len(need_full)}, need_incr={len(need_incr)}, up_to_date={len(up_to_date)}")

    total_inserted = 0
    total_failed = []

    INCR_BATCH = 200   # Download 200 symbols at once for incremental
    FULL_BATCH = 50    # Smaller batches for full history (more data per symbol)
    INCR_PAUSE = 1.0   # 1s between incremental batches (tiny data)
    FULL_PAUSE = 2.0   # 2s between full-history batches

    def _download_and_insert(batch_syms, start_date=None, period=None, pause=1.0):
        """Download a batch and insert into DB. Returns (inserted_count, failed_list)."""
        yq_batch = [s.replace('.', '-').replace('$', '-P') for s in batch_syms]
        mapping = dict(zip(yq_batch, batch_syms))
        n_ins, n_fail = 0, []

        for attempt in range(1, 4):
            try:
                kwargs = dict(tickers=yq_batch, interval="1d", auto_adjust=False,
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
            logging.warning(f"[SMART] batch download returned no data: {batch_syms[:3]}...")
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
                    sub = sub[sub.get("open", pd.Series(dtype=float)).notna()] if "open" in sub.columns else sub

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

    # Process incremental updates (fast path)
    if need_incr:
        # Group by last_date to minimize API calls (symbols with same last_date → one batch)
        from collections import defaultdict
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
                logging.info(f"[SMART] incremental batch {i//INCR_BATCH+1}: inserted {ins} rows, {len(fail)} failed")

    # Process symbols needing full history (slow path, first-time load)
    if need_full:
        logging.info(f"[SMART] full history: loading {len(need_full)} symbols without existing data")
        for i in range(0, len(need_full), FULL_BATCH):
            batch = need_full[i:i+FULL_BATCH]
            ins, fail = _download_and_insert(batch, period="max", pause=FULL_PAUSE)
            total_inserted += ins
            total_failed.extend(fail)
            logging.info(f"[SMART] full batch {i//FULL_BATCH+1}/{(len(need_full)+FULL_BATCH-1)//FULL_BATCH}: inserted {ins} rows")

    elapsed = time.time() - start_wall
    logging.info(f"[SMART] {table_name}: DONE in {elapsed:.1f}s — inserted {total_inserted} rows, {len(total_failed)} failed")
    if total_failed:
        logging.warning(f"[SMART] {table_name}: failed symbols: {total_failed[:20]}{'...' if len(total_failed)>20 else ''}")

    return len(symbols), total_inserted, total_failed


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Load daily price data for stocks and ETFs')
    parser.add_argument('--historical', action='store_true',
                       help='Load full historical data (period="max")')
    parser.add_argument('--incremental', action='store_true',
                       help='Load recent data only (period="3mo")')
    parser.add_argument('--smart', action='store_true',
                       help='Smart incremental: only fetch missing data per symbol. FAST (5-10 min vs 3-4 hours).')
    parser.add_argument('--symbol-range', type=str, default=None,
                       help='Symbol range for parallel loading (e.g., "A-L", "M-Z", "AA-AZ", "BA-ZZ", "ETF")')
    args = parser.parse_args()

    # Determine data period based on arguments
    if args.smart:
        logging.info("Running in SMART mode - incremental per-symbol fetch (40-60x faster for updates)")
    elif args.historical:
        DATA_PERIOD = "max"
        logging.info("Running in HISTORICAL mode - loading full historical data")
    elif args.incremental:
        DATA_PERIOD = "3mo"
        logging.info("Running in INCREMENTAL mode - loading recent 3 months of data")
    else:
        DATA_PERIOD = "3mo"  # Default to recent data to prevent memory exhaustion
        logging.info("Running in DEFAULT mode - loading recent 3 months of data (use --historical for full history)")

    log_mem("startup")

    # Connect to DB with timeouts to prevent hanging
    cfg  = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"],
        connect_timeout=30,
        options='-c statement_timeout=600000'
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Create tables if they don't exist (don't drop - allow incremental loading)
    logging.info("Ensuring price_daily table exists…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_daily (
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

    # Create index for efficient lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_price_daily_symbol ON price_daily(symbol);")

    # Create unique constraint for ON CONFLICT upserts
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_price_daily_symbol_date ON price_daily(symbol, date);")

    logging.info("Ensuring etf_price_daily table exists…")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etf_price_daily (
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

    # Create index for efficient lookups
    cur.execute("CREATE INDEX IF NOT EXISTS idx_etf_price_daily_symbol ON etf_price_daily(symbol);")

    # Create unique constraint for ON CONFLICT upserts
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_etf_price_daily_symbol_date ON etf_price_daily(symbol, date);")

    conn.commit()

    # Load stock symbols - optionally filtered by symbol range for parallel processing
    # If --symbol-range is specified, only load symbols in that range
    if args.symbol_range and args.symbol_range != "ETF":
        # For ranges like A-L, M-Z, AA-AZ, etc.
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol;")
        all_syms = [r["symbol"] for r in cur.fetchall()]
        stock_syms = filter_symbols_by_range(all_syms, args.symbol_range)
        logging.info(f"Loading daily prices for {len(stock_syms)} stock symbols in range {args.symbol_range}")
    else:
        # Load all stock symbols
        cur.execute("SELECT symbol FROM stock_symbols;")
        stock_syms = [r["symbol"] for r in cur.fetchall()]
        logging.info(f"Loading daily prices for ALL {len(stock_syms)} stock symbols (daily update mode)")

    if args.smart:
        t_s, i_s, f_s = load_prices_smart("price_daily", stock_syms, cur, conn)
    else:
        t_s, i_s, f_s = load_prices("price_daily", stock_syms, cur, conn)

    # Load ETF symbols (from etf_symbols table if it exists)
    # Only load if --symbol-range is not specified or is "ETF"
    if not args.symbol_range or args.symbol_range == "ETF":
        try:
            cur.execute("SELECT symbol FROM etf_symbols;")
            etf_syms = [r["symbol"] for r in cur.fetchall()]
            logging.info(f"Loading daily prices for ALL {len(etf_syms)} ETF symbols (daily update mode)")

            if args.smart:
                t_w, i_w, f_w = load_prices_smart("etf_price_daily", etf_syms, cur, conn)
            else:
                t_w, i_w, f_w = load_prices("etf_price_daily", etf_syms, cur, conn)
        except psycopg2.errors.UndefinedTable:
            logging.warning(" etf_symbols table does not exist - skipping ETF price loading")
            t_w, i_w, f_w = 0, 0, 0
    else:
        logging.info(f"Skipping ETF loading (--symbol-range={args.symbol_range})")
        t_w, i_w, f_w = 0, 0, 0

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
    logging.info("All done.")
# Deploy trigger 20251219
