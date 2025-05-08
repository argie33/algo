#!/usr/bin/env python3
import os
import re
import csv
import json
import logging
import requests
import boto3
import psycopg2
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger("loadstocksymbols")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)

# ─── Configuration ───────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
NASDAQ_URL    = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
OTHER_URL     = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# any regexes for classifying “other security”:
patterns = [
    # e.g. r"\bpreferred\b", r"\bredeem\b"
]

def get_http_session():
    """Return a requests.Session with retry logic."""
    s = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429,500,502,503,504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

def fetch_text(url: str) -> str:
    """Download a text file over HTTP and return its body."""
    logger.info("Downloading %s", url)
    resp = get_http_session().get(url, timeout=(5,15))
    resp.raise_for_status()
    return resp.text

def parse_listed(text: str, source: str) -> list[dict]:
    """
    Robustly parse a Nasdaq pipe-delimited listing from its raw text.
    - Finds the real header row (which may be buried after metadata)
    - Uses that header for csv.DictReader
    - Dynamically picks Symbol/ACT Symbol/NASDAQ Symbol
    - Returns a list of dicts with our desired fields
    """
    lines = text.splitlines()
    # 1) locate the true header row (contains "Security Name" and at least one "Symbol")
    header_idx = None
    for i, line in enumerate(lines):
        if "Security Name" in line and "|" in line:
            header_idx = i
            break
    if header_idx is None:
        logger.error("[%s] could not find header row", source)
        return []

    data_lines = lines[header_idx:]
    reader = csv.DictReader(data_lines, delimiter="|")
    headers = reader.fieldnames or []

    # 2) pick the correct symbol column
    for cand in ("Symbol", "ACT Symbol", "NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        logger.error("[%s] no Symbol column in headers %s", source, headers)
        return []

    records = []
    for row in reader:
        sym = row.get(sym_key, "").strip()
        # skip blank rows or the header row repeated
        if not sym or sym == sym_key:
            continue

        name = row.get("Security Name", "").strip()
        try:
            lot = int(row.get("Round Lot Size", "") or 0)
        except ValueError:
            lot = None

        is_other = any(
            re.search(p, name, flags=re.IGNORECASE) for p in patterns
        )

        records.append({
            "symbol":         sym,
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue", "").strip(),
            "round_lot_size": lot,
            "security_type":  "other security" if is_other else "standard"
        })

    logger.info("[%s] Parsed %d rows", source, len(records))
    return records

def get_db_connection():
    """Retrieve DB credentials from Secrets Manager and return a psycopg2 connection."""
    sm   = boto3.client("secretsmanager")
    sec  = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    conf = json.loads(sec["SecretString"])
    return psycopg2.connect(
        host     = conf["host"],
        port     = int(conf["port"]),
        dbname   = conf["dbname"],
        user     = conf["username"],
        password = conf["password"],
        sslmode  = "require"
    )

def main():
    # ── Fetch & parse both lists ───────────────────────────────────────────────
    nas = parse_listed(fetch_text(NASDAQ_URL), "NASDAQ")
    oth = parse_listed(fetch_text(OTHER_URL),  "Other")

    logger.info("Raw counts → NASDAQ=%d, Other=%d", len(nas), len(oth))

    # ── Combine & dedupe on (symbol,exchange) ─────────────────────────────────
    seen   = set()
    unique = []
    for rec in nas + oth:
        key = (rec["symbol"], rec["exchange"])
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    logger.info("After dedupe → %d unique records", len(unique))

    # ── Flag core_security & attach to each record ───────────────────────────
    for rec in unique:
        rec["core_security"] = "yes" if "$" not in rec["symbol"] else "no"

    # ── Drop & recreate table, then bulk insert ────────────────────────────────
    conn = get_db_connection()
    with conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS stock_symbols;")
        cur.execute("""
        CREATE TABLE stock_symbols (
          symbol          VARCHAR(50) PRIMARY KEY,
          security_name   TEXT,
          exchange        VARCHAR(20),
          test_issue      CHAR(1),
          round_lot_size  INT,
          security_type   VARCHAR(20),
          core_security   CHAR(3)
        );
        """)
        insert_sql = """
        INSERT INTO stock_symbols
          (symbol, security_name, exchange, test_issue,
           round_lot_size, security_type, core_security)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ;
        """
        cur.executemany(insert_sql, [
            (
                r["symbol"],
                r["security_name"],
                r["exchange"],
                r["test_issue"],
                r["round_lot_size"],
                r["security_type"],
                r["core_security"]
            ) for r in unique
        ])

        # update last_updated
        cur.execute("""
        CREATE TABLE IF NOT EXISTS last_updated (
          script_name VARCHAR(255) PRIMARY KEY,
          last_run    TIMESTAMPTZ
        );
        """)
        cur.execute("""
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
        """, (os.path.basename(__file__),))
    conn.close()

    logger.info("✅ Successfully wrote %d symbols", len(unique))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        raise
