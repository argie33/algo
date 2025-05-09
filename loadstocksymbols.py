#!/usr/bin/env python3
import os
import sys
import re
import logging
from ftplib import FTP

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols")

# ─── Postgres RDS config ────────────────────────────────────────────────────────
POSTGRES_HOST     = os.environ["POSTGRES_HOST"]
POSTGRES_PORT     = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.environ["POSTGRES_DB"]
POSTGRES_USER     = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]

# ─── FTP config ────────────────────────────────────────────────────────────────
FTP_HOST    = "ftp.nasdaqtrader.com"
FTP_DIR     = "symboldirectory"
NASDAQ_FILE = "nasdaqlisted.txt"
OTHER_FILE  = "otherlisted.txt"

# ─── Filter patterns ───────────────────────────────────────────────────────────
patterns = [
    r"\bpreferred\b",
    r"\bredeemable warrant(s)?\b",
    # … (all your other patterns here) …
    r"\bnasdaq symbology\b",
]

def should_filter(name: str) -> bool:
    for pat in patterns:
        if re.search(pat, name, flags=re.IGNORECASE):
            return True
    return False

def download_ftp_file(fname: str) -> str:
    logger.info(f"FTP → downloading {fname}")
    ftp = FTP(FTP_HOST, timeout=30)
    ftp.login()
    ftp.cwd(FTP_DIR)
    lines = []
    ftp.retrlines(f"RETR {fname}", callback=lines.append)
    ftp.quit()
    return "\n".join(lines)

def parse_nasdaq_listed(text: str) -> pd.DataFrame:
    logger.info("Parsing NASDAQ-listed")
    df = pd.read_csv(pd.io.common.StringIO(text), sep="|", dtype=str)
    recs = []
    for _, r in df.iterrows():
        if r["Symbol"].startswith("File Creation Time"):
            continue
        name = r["Security Name"].strip()
        is_other = (r["ETF"].upper()=="Y") or should_filter(name)
        recs.append({
            "symbol": r["Symbol"].strip(),
            "security_name": name,
            "exchange": "NASDAQ",
            "cqs_symbol": None,
            "market_category": r["Market Category"].strip(),
            "test_issue": r["Test Issue"].strip(),
            "financial_status": r["Financial Status"].strip(),
            "round_lot_size": pd.to_numeric(r["Round Lot Size"], errors="coerce"),
            "etf": r["ETF"].strip(),
            "secondary_symbol": r["NextShares"].strip(),
            "symbol_type": "other" if is_other else "primary"
        })
    return pd.DataFrame(recs)

def parse_other_listed(text: str) -> pd.DataFrame:
    logger.info("Parsing Other-listed")
    exch_map = {
        "A":"American Stock Exchange",
        "N":"New York Stock Exchange",
        "P":"NYSE Arca",
        "Z":"BATS Global Markets"
    }
    df = pd.read_csv(pd.io.common.StringIO(text), sep="|", dtype=str)
    recs = []
    for _, r in df.iterrows():
        if r["ACT Symbol"].startswith("File Creation Time"):
            continue
        name = r["Security Name"].strip()
        is_other = (r["ETF"].upper()=="Y") or should_filter(name)
        recs.append({
            "symbol": r["ACT Symbol"].strip(),
            "security_name": name,
            "exchange": exch_map.get(r["Exchange"].strip(), r["Exchange"].strip()),
            "cqs_symbol": r["CQS Symbol"].strip(),
            "market_category": None,
            "test_issue": r["Test Issue"].strip(),
            "financial_status": None,
            "round_lot_size": pd.to_numeric(r["Round Lot Size"], errors="coerce"),
            "etf": r["ETF"].strip(),
            "secondary_symbol": r["NASDAQ Symbol"].strip(),
            "symbol_type": "other" if is_other else "primary"
        })
    return pd.DataFrame(recs)

def drop_and_create_table():
    logger.info("Rebuilding stock_symbols table")
    ddl = """
    DROP TABLE IF EXISTS stock_symbols;
    CREATE TABLE stock_symbols (
      symbol TEXT PRIMARY KEY,
      security_name TEXT,
      exchange TEXT,
      cqs_symbol TEXT,
      market_category TEXT,
      test_issue CHAR(1),
      financial_status TEXT,
      round_lot_size INT,
      etf CHAR(1),
      secondary_symbol TEXT,
      symbol_type TEXT
    );
    """
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
    conn.close()

def insert_records(df: pd.DataFrame):
    cols = [
        "symbol","security_name","exchange","cqs_symbol",
        "market_category","test_issue","financial_status",
        "round_lot_size","etf","secondary_symbol","symbol_type"
    ]
    vals = [tuple(x) for x in df[cols].itertuples(index=False, name=None)]
    sql = f"""
      INSERT INTO stock_symbols {tuple(cols)} VALUES %s
      ON CONFLICT (symbol) DO UPDATE SET
        security_name = EXCLUDED.security_name,
        exchange = EXCLUDED.exchange,
        cqs_symbol = EXCLUDED.cqs_symbol,
        market_category = EXCLUDED.market_category,
        test_issue = EXCLUDED.test_issue,
        financial_status = EXCLUDED.financial_status,
        round_lot_size = EXCLUDED.round_lot_size,
        etf = EXCLUDED.etf,
        secondary_symbol = EXCLUDED.secondary_symbol,
        symbol_type = EXCLUDED.symbol_type;
    """
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    with conn:
        with conn.cursor() as cur:
            logger.info(f"Upserting {len(vals)} rows")
            execute_values(cur, sql, vals, page_size=500)
    conn.close()

def update_last_updated():
    logger.info("Stamping last_updated")
    sql = """
    CREATE TABLE IF NOT EXISTS last_updated (
      script_name TEXT PRIMARY KEY,
      last_updated TIMESTAMPTZ
    );
    INSERT INTO last_updated (script_name,last_updated)
      VALUES (%s,NOW())
      ON CONFLICT (script_name) DO UPDATE
        SET last_updated=EXCLUDED.last_updated;
    """
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql, (os.path.basename(__file__),))
    conn.close()

def job_nasdaq():
    txt = download_ftp_file(NASDAQ_FILE)
    df = parse_nasdaq_listed(txt)
    insert_records(df)

def job_other():
    txt = download_ftp_file(OTHER_FILE)
    df = parse_other_listed(txt)
    insert_records(df)

def main():
    # 1) Rebuild table once
    drop_and_create_table()

    # 2) Run NASDAQ job
    logger.info("=== JOB: NASDAQ ===")
    job_nasdaq()

    # 3) Run OTHER job
    logger.info("=== JOB: OTHER ===")
    job_other()

    # 4) Stamp
    update_last_updated()
    logger.info("All done.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
