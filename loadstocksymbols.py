#!/usr/bin/env python3
import os
import re
import json
import logging
import urllib.request
import requests
import boto3
import pandas as pd

from io import StringIO
from sqlalchemy import create_engine, text
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from sqlalchemy.exc import SQLAlchemyError

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger("loadstocksymbols")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)

# ─── Configuration ───────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
NASDAQ_URL    = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_FTP_URL = "ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt"
PATTERNS      = [
    # e.g. r"\bpreferred\b", r"\bredeem\b"
]

def fetch_http(url: str) -> str:
    """Download a text file via HTTP with retries."""
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1,
                    status_forcelist=[429,500,502,503,504],
                    allowed_methods=["GET"])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))

    logger.info("Downloading via HTTP: %s", url)
    resp = session.get(url, timeout=(5,15))
    resp.raise_for_status()
    return resp.text

def fetch_ftp(url: str) -> str:
    """Download a text file via FTP using urllib."""
    logger.info("Downloading via FTP: %s", url)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def parse_to_df(text: str, source: str) -> pd.DataFrame:
    """
    Parse a Nasdaq pipe-delimited listing into a DataFrame.
    - Drops any line starting with 'File Creation Time'
    - Dynamically determines the symbol column
    - Filters out ETFs
    - Classifies security_type
    """
    # drop metadata lines
    lines = [L for L in text.splitlines() if not L.startswith("File Creation Time")]
    df = pd.read_csv(StringIO("\n".join(lines)), sep="|", dtype=str)

    # find the symbol column
    sym_col = next((c for c in df.columns if c in ("Symbol","ACT Symbol","NASDAQ Symbol")), None)
    if not sym_col:
        raise ValueError(f"[{source}] could not find symbol column; headers={df.columns.tolist()}")

    # drop the header-row reappearing in the body
    df = df[df[sym_col] != sym_col]

    # rename & select our fields
    df = df.rename(columns={
        sym_col:         "symbol",
        "Security Name": "security_name",
        "Test Issue":    "test_issue",
        "Round Lot Size":"round_lot_size"
    })[
        ["symbol", "security_name", "Test Issue", "round_lot_size", "ETF"]
    ]

    # filter out ETFs
    df = df[df["ETF"].str.upper() != "Y"]

    # fill and cast
    df["round_lot_size"] = pd.to_numeric(df["round_lot_size"], errors="coerce").fillna(0).astype(int)
    df["exchange"]       = source
    df["security_type"]  = df["security_name"].apply(
        lambda n: "other security" if any(re.search(p, n, flags=re.IGNORECASE) for p in PATTERNS)
                     else "standard"
    )
    df = df.drop(columns=["ETF"])

    logger.info("[%s] parsed %d rows → columns=%s", source, len(df), df.columns.tolist())
    return df

def get_db_engine():
    """Retrieve DB creds from SecretsManager and build an SQLAlchemy engine."""
    sm   = boto3.client("secretsmanager")
    sec  = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    conf = json.loads(sec["SecretString"])
    uri  = (
        f"postgresql+psycopg2://{conf['username']}:{conf['password']}"
        f"@{conf['host']}:{conf['port']}/{conf['dbname']}"
    )
    return create_engine(uri, connect_args={"sslmode":"require"})

def main():
    # ── Fetch & parse both lists ────────────────────────────────────────────────
    nas_text = fetch_http(NASDAQ_URL)
    oth_text = fetch_ftp(OTHER_FTP_URL)

    df_nas = parse_to_df(nas_text, "NASDAQ")
    df_oth = parse_to_df(oth_text,  "Other")
    logger.info("Counts → NASDAQ=%d, Other=%d", len(df_nas), len(df_oth))

    # ── Concat & dedupe on (symbol,exchange) ──────────────────────────────────
    df = pd.concat([df_nas, df_oth], ignore_index=True)
    before = len(df)
    df = df.drop_duplicates(subset=["symbol","exchange"], keep="first")
    logger.info("Deduped %d → %d rows", before, len(df))

    # ── Flag core_security & attach source_file ──────────────────────────────
    df["core_security"] = df["symbol"].apply(lambda s: "yes" if "$" not in s else "no")
    df["source_file"]   = df["exchange"]

    # ── Drop & recreate table, then bulk load ────────────────────────────────
    engine = get_db_engine()
    with engine.begin() as conn:
        # drop + create
        conn.execute(text("DROP TABLE IF EXISTS stock_symbols;"))
        conn.execute(text("""
            CREATE TABLE stock_symbols (
              symbol          VARCHAR(50) PRIMARY KEY,
              security_name   TEXT,
              exchange        VARCHAR(20),
              test_issue      CHAR(1),
              round_lot_size  INT,
              security_type   VARCHAR(20),
              core_security   CHAR(3),
              source_file     TEXT
            );
        """))

        # bulk insert via pandas.to_sql (append into freshly created table)
        df.to_sql(
            "stock_symbols",
            con=conn,
            if_exists="append",
            index=False
        )

        # update last_updated
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS last_updated (
              script_name VARCHAR(255) PRIMARY KEY,
              last_run    TIMESTAMPTZ
            );
        """))
        conn.execute(
            text("INSERT INTO last_updated (script_name,last_run) VALUES (:n,NOW()) "
                 "ON CONFLICT (script_name) DO UPDATE SET last_run=EXCLUDED.last_run"),
            {"n": os.path.basename(__file__)}
        )

    logger.info("✅ Wrote %d symbols to stock_symbols", len(df))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("❌ loadstocksymbols failed") 
        raise
