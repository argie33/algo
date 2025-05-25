#!/usr/bin/env python3
import sys
import time
import logging
import functools
import os
import json
import resource
import gc

import boto3
import psycopg2
from psycopg2.extras import DictCursor
import yfinance as yf
import pandas as pd

# -------------------------------
# Script metadata & logging setup
# -------------------------------
SCRIPT_NAME = "loadfinancialdata.py"
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# -------------------------------
# Memory-logging helper (RSS in MB)
# -------------------------------
def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage/1024 if sys.platform.startswith("linux") else usage/(1024*1024)

def log_mem(stage: str):
    logger.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")

# -------------------------------
# Retry decorator
# -------------------------------
def retry(max_attempts=3, initial_delay=2, backoff=2):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(symbol, conn, *args, **kwargs):
            attempts, delay = 0, initial_delay
            while attempts < max_attempts:
                try:
                    return f(symbol, conn, *args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.error(
                        f"{f.__name__} failed for {symbol} "
                        f"(attempt {attempts}/{max_attempts}): {e}",
                        exc_info=True
                    )
                    if attempts < max_attempts:
                        time.sleep(delay)
                        delay *= backoff
            raise RuntimeError(
                f"All {max_attempts} attempts failed for {f.__name__} on {symbol}"
            )
        return wrapper
    return decorator

# -------------------------------
# Clean NaN → None
# -------------------------------
def clean(v):
    return None if (pd.isna(v) or v is None) else v

# -------------------------------
# Helper to create a table
# -------------------------------
def create_table(cur, tbl_name, fields):
    """
    fields: list of numeric field names (strings)
    Builds columns: symbol, date, then each field as DOUBLE PRECISION
    """
    cols_ddl = ",\n    ".join(f'"{f}" DOUBLE PRECISION' for f in fields)
    cur.execute(f"DROP TABLE IF EXISTS {tbl_name};")
    cur.execute(f"""
        CREATE TABLE {tbl_name} (
          symbol     VARCHAR(10) NOT NULL,
          date       DATE        NOT NULL,
          {cols_ddl},
          fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY(symbol, date)
        );
    """)

# -------------------------------
# Dynamically create all tables
# -------------------------------
def ensure_tables_dynamic(conn, sample_symbol="AAPL"):
    tkr = yf.Ticker(sample_symbol)
    bs_ann = tkr.balance_sheet
    bs_qt  = tkr.quarterly_balance_sheet
    is_ann = tkr.financials
    is_qt  = tkr.quarterly_financials
    cf_ann = tkr.cashflow
    cf_qt  = tkr.quarterly_cashflow

    with conn.cursor() as cur:
        # Balance Sheet
        create_table(cur, "balance_sheet_annual", list(bs_ann.index.astype(str)))
        create_table(cur, "balance_sheet_quarterly", list(bs_qt.index.astype(str)))
        create_table(cur, "balance_sheet_ttm", list(bs_qt.index.astype(str)))

        # Income Statement
        create_table(cur, "income_statement_annual", list(is_ann.index.astype(str)))
        create_table(cur, "income_statement_quarterly", list(is_qt.index.astype(str)))
        create_table(cur, "income_statement_ttm", list(is_qt.index.astype(str)))

        # Cash Flow
        create_table(cur, "cash_flow_annual", list(cf_ann.index.astype(str)))
        create_table(cur, "cash_flow_quarterly", list(cf_qt.index.astype(str)))
        create_table(cur, "cash_flow_ttm", list(cf_qt.index.astype(str)))

        # Combined financials: intersect annual sets
        fin_ann = sorted(
            set(bs_ann.index.astype(str)) &
            set(is_ann.index.astype(str)) &
            set(cf_ann.index.astype(str))
        )
        create_table(cur, "financials", fin_ann)

        # Combined quarterly/tTM: intersect quarterly sets
        fin_qt = sorted(
            set(bs_qt.index.astype(str)) &
            set(is_qt.index.astype(str)) &
            set(cf_qt.index.astype(str))
        )
        create_table(cur, "financials_quarterly", fin_qt)
        create_table(cur, "financials_ttm", fin_qt)

        # last_updated
        cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
              script_name VARCHAR(255) PRIMARY KEY,
              last_run    TIMESTAMPTZ NOT NULL
            );
        """)
    conn.commit()

# -------------------------------
# Generic upsert; returns number of rows
# -------------------------------
def upsert(table, cols, rows, conn):
    if not rows:
        return 0
    col_list = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join(f'{c}=EXCLUDED.{c}' for c in cols if c not in ("symbol","date"))
    sql = f"""
      INSERT INTO {table} ({col_list})
      VALUES ({placeholders})
      ON CONFLICT(symbol,date) DO UPDATE
        SET {updates}, fetched_at=NOW();
    """
    with conn.cursor() as cur:
        cur.executemany(sql, [[r[c] for c in cols] for r in rows])
    return len(rows)

# -------------------------------
# Build rows + field list from df
# -------------------------------
def build_rows_and_fields(df, symbol):
    fields = list(df.index.astype(str))
    rows = []
    for dt in sorted(df.columns):
        r = {"symbol": symbol, "date": dt.date()}
        for f in fields:
            r[f] = clean(df.at[f, dt]) if f in df.index else None
        rows.append(r)
    return rows, fields

# -------------------------------
# Process one symbol; returns per-table counts
# -------------------------------
@retry()
def process_symbol(symbol, conn):
    start = time.time()
    log_mem(f"{symbol} start")

    yf_sym = symbol.upper().replace(".", "-")
    tkr = yf.Ticker(yf_sym)

    # raw DataFrames
    bs_ann = tkr.balance_sheet
    bs_qt  = tkr.quarterly_balance_sheet
    is_ann = tkr.financials
    is_qt  = tkr.quarterly_financials
    cf_ann = tkr.cashflow
    cf_qt  = tkr.quarterly_cashflow

    metrics = {"symbol": symbol, "tables": {}}

    gc.disable()
    try:
        # Balance Sheet annual
        rows, fields = build_rows_and_fields(bs_ann, symbol)
        cnt = upsert("balance_sheet_annual", ["symbol","date"]+fields, rows, conn)
        metrics["tables"]["balance_sheet_annual"] = cnt

        # Balance Sheet quarterly
        rows_q, fields_q = build_rows_and_fields(bs_qt, symbol)
        cnt = upsert("balance_sheet_quarterly", ["symbol","date"]+fields_q, rows_q, conn)
        metrics["tables"]["balance_sheet_quarterly"] = cnt

        # Balance Sheet TTM = latest quarterly
        if rows_q:
            cnt = upsert("balance_sheet_ttm", ["symbol","date"]+fields_q, [rows_q[-1]], conn)
            metrics["tables"]["balance_sheet_ttm"] = cnt

        # Income Statement annual
        rows, fields = build_rows_and_fields(is_ann, symbol)
        cnt = upsert("income_statement_annual", ["symbol","date"]+fields, rows, conn)
        metrics["tables"]["income_statement_annual"] = cnt

        # Income Statement quarterly
        rows_q, fields_q = build_rows_and_fields(is_qt, symbol)
        cnt = upsert("income_statement_quarterly", ["symbol","date"]+fields_q, rows_q, conn)
        metrics["tables"]["income_statement_quarterly"] = cnt

        # Income Statement TTM = sum last 4 quarters
        if len(rows_q) >= 4:
            last4 = rows_q[-4:]
            ttm = {"symbol": symbol, "date": last4[-1]["date"]}
            for f in fields_q:
                ttm[f] = sum(r[f] or 0 for r in last4)
            cnt = upsert("income_statement_ttm", ["symbol","date"]+fields_q, [ttm], conn)
            metrics["tables"]["income_statement_ttm"] = cnt

        # Cash Flow annual
        rows, fields = build_rows_and_fields(cf_ann, symbol)
        cnt = upsert("cash_flow_annual", ["symbol","date"]+fields, rows, conn)
        metrics["tables"]["cash_flow_annual"] = cnt

        # Cash Flow quarterly
        rows_q, fields_q = build_rows_and_fields(cf_qt, symbol)
        cnt = upsert("cash_flow_quarterly", ["symbol","date"]+fields_q, rows_q, conn)
        metrics["tables"]["cash_flow_quarterly"] = cnt

        # Cash Flow TTM = sum last 4 quarters
        if len(rows_q) >= 4:
            last4 = rows_q[-4:]
            ttm = {"symbol": symbol, "date": last4[-1]["date"]}
            for f in fields_q:
                ttm[f] = sum(r[f] or 0 for r in last4)
            cnt = upsert("cash_flow_ttm", ["symbol","date"]+fields_q, [ttm], conn)
            metrics["tables"]["cash_flow_ttm"] = cnt

        # Combined financials annual
        rows_bs, _ = build_rows_and_fields(bs_ann, symbol)
        rows_is, _ = build_rows_and_fields(is_ann, symbol)
        rows_cf, _ = build_rows_and_fields(cf_ann, symbol)
        # intersect fields
        ann_fields = sorted(
            set(rows_bs[0].keys()) & set(rows_is[0].keys()) & set(rows_cf[0].keys())
        )
        ann_fields = [f for f in ann_fields if f not in ("symbol","date")]
        combined_ann = []
        dates = sorted(set(r["date"] for r in rows_bs))
        for dt in dates:
            entry = {"symbol": symbol, "date": dt}
            for f in ann_fields:
                # pick from bs if present, else is, else cf
                entry[f] = (
                    next((r[f] for r in rows_bs if r["date"]==dt), None)
                    or next((r[f] for r in rows_is if r["date"]==dt), None)
                    or next((r[f] for r in rows_cf if r["date"]==dt), None)
                )
            combined_ann.append(entry)
        cnt = upsert("financials", ["symbol","date"]+ann_fields, combined_ann, conn)
        metrics["tables"]["financials"] = cnt

        # Combined quarterly + TTM analogous...
        rows_bs, _ = build_rows_and_fields(bs_qt, symbol)
        rows_is, _ = build_rows_and_fields(is_qt, symbol)
        rows_cf, _ = build_rows_and_fields(cf_qt, symbol)
        q_fields = sorted(
            set(rows_bs[0].keys()) & set(rows_is[0].keys()) & set(rows_cf[0].keys())
        )
        q_fields = [f for f in q_fields if f not in ("symbol","date")]
        combined_q = []
        dates = sorted(set(r["date"] for r in rows_bs))
        for dt in dates:
            entry = {"symbol": symbol, "date": dt}
            for f in q_fields:
                entry[f] = (
                    next((r[f] for r in rows_bs if r["date"]==dt), None)
                    or next((r[f] for r in rows_is if r["date"]==dt), None)
                    or next((r[f] for r in rows_cf if r["date"]==dt), None)
                )
            combined_q.append(entry)
        cnt = upsert("financials_quarterly", ["symbol","date"]+q_fields, combined_q, conn)
        metrics["tables"]["financials_quarterly"] = cnt

        if len(combined_q) >= 4:
            last4 = combined_q[-4:]
            ttm = {"symbol": symbol, "date": last4[-1]["date"]}
            for f in q_fields:
                ttm[f] = sum(r[f] or 0 for r in last4)
            cnt = upsert("financials_ttm", ["symbol","date"]+q_fields, [ttm], conn)
            metrics["tables"]["financials_ttm"] = cnt

        conn.commit()
    finally:
        gc.enable()
        log_mem(f"{symbol} end ({time.time()-start:.1f}s)")
    return metrics

# -------------------------------
# Stamp last run
# -------------------------------
def update_last_run(conn):
    with conn.cursor() as cur:
        cur.execute("""
          INSERT INTO last_updated (script_name, last_run)
          VALUES (%s, NOW())
          ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, (SCRIPT_NAME,))
    conn.commit()

# -------------------------------
# DB config via Secrets Manager
# -------------------------------
def get_db_config():
    sec = json.loads(
      boto3.client("secretsmanager")
           .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    return {
      "host": sec["host"],
      "port": int(sec.get("port", 5432)),
      "user": sec["username"],
      "password": sec["password"],
      "dbname": sec["dbname"]
    }

# -------------------------------
# Main
# -------------------------------
def main():
    log_mem("startup")
    overall_start = time.time()

    # Connect
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"],
        user=cfg["user"], password=cfg["password"],
        dbname=cfg["dbname"], sslmode="require",
        cursor_factory=DictCursor
    )
    conn.autocommit = False

    # Create tables dynamically
    logger.info("Ensuring tables exist via dynamic introspection…")
    log_mem("before-ensure")
    ensure_tables_dynamic(conn)
    log_mem("after-ensure")

    # Load symbols
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol;")
        symbols = [r["symbol"] for r in cur.fetchall()]

    total = len(symbols)
    processed = 0
    failures = []
    aggregate = {}

    for sym in symbols:
        try:
            metrics = process_symbol(sym, conn)
            for tbl, cnt in metrics["tables"].items():
                aggregate[tbl] = aggregate.get(tbl, 0) + cnt
            processed += 1
        except Exception:
            logger.exception(f"Failed to process {sym}")
            failures.append(sym)

    # Finalize
    update_last_run(conn)
    conn.close()

    peak = get_rss_mb()
    logger.info(f"[MEM] peak RSS: {peak:.1f} MB")
    logger.info(f"Symbols processed: {processed}/{total}")
    if failures:
        logger.warning(f"Symbols failed: {failures}")
    for tbl, cnt in aggregate.items():
        logger.info(f"{tbl}: upserted {cnt} rows total")
    logger.info(f"Total elapsed: {time.time()-overall_start:.1f} seconds")

if __name__ == "__main__":
    main()
