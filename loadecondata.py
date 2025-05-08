#!/usr/bin/env python3
import os
import re
import csv
import json
import logging

import requests
import boto3
import psycopg  # ← psycopg3, not psycopg2
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger("loadstocksymbols")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)

# ─── Config ──────────────────────────────────────────────────────────────────────
SCRIPT_NAME   = os.path.basename(__file__)
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

# ─── Data sources & exclusion patterns ────────────────────────────────────────────
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
patterns = [
    # … all your regex patterns here …
    r"\bpreferred\b",
    r"\bredeemable warrant(s)?\b",
    # (etc)
]

def get_requests_session():
    s = requests.Session()
    r = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429,500,502,503,504],
        allowed_methods=["GET"]
    )
    a = HTTPAdapter(max_retries=r)
    s.mount("http://", a)
    s.mount("https://", a)
    return s

def download_text_file(url):
    logger.info("Downloading %s", url)
    resp = get_requests_session().get(url, timeout=(5,15))
    resp.raise_for_status()
    return resp.text

def parse_listed(text, source):
    rows = []
    key = "Symbol" if source == "NASDAQ" else "ACT Symbol"
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        # skip header/footer lines
        if row[key].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        # skip ETFs
        if row.get("ETF","").upper() == "Y":
            continue
        is_other = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)
        try:
            lot = int(row.get("Round Lot Size","0") or 0)
        except ValueError:
            lot = None
        rows.append({
            "symbol":         row[key].strip(),
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue","").strip(),
            "round_lot_size": lot,
            "security_type":  "other security" if is_other else "standard"
        })
    logger.info("Parsed %d rows from %s", len(rows), source)
    return rows

def dedupe(records):
    seen = {}
    for r in records:
        seen.setdefault(r["symbol"], r)
    return list(seen.values())

# ─── Secrets & DB connection ────────────────────────────────────────────────────
_secret = None
_conn   = None

def get_db_creds():
    global _secret
    if _secret is None:
        sm = boto3.client("secretsmanager")
        v  = sm.get_secret_value(SecretId=DB_SECRET_ARN)
        _secret = json.loads(v["SecretString"])
    return (
        _secret["username"],
        _secret["password"],
        _secret["host"],
        int(_secret["port"]),
        _secret["dbname"]
    )

def _get_conn():
    global _conn
    if _conn is None:
        user, pwd, host, port, db = get_db_creds()
        logger.info("Connecting to Postgres at %s:%s/%s", host, port, db)
        _conn = psycopg.connect(
            host=host,
            port=port,
            dbname=db,
            user=user,
            password=pwd,
            sslmode="require"
        )
    return _conn

def insert_into_postgres(records):
    conn = _get_conn()
    cur  = conn.cursor()
    # create tables if missing
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stock_symbols (
      symbol          VARCHAR(50) PRIMARY KEY,
      security_name   TEXT,
      exchange        VARCHAR(20),
      test_issue      CHAR(1),
      round_lot_size  INT,
      security_type   VARCHAR(20)
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
      script_name VARCHAR(255) PRIMARY KEY,
      last_run    TIMESTAMPTZ
    );
    """)
    # upsert into stock_symbols
    sql = """
    INSERT INTO stock_symbols
      (symbol,security_name,exchange,test_issue,round_lot_size,security_type)
    VALUES (%s,%s,%s,%s,%s,%s)
    ON CONFLICT(symbol) DO UPDATE SET
      security_name  = EXCLUDED.security_name,
      exchange       = EXCLUDED.exchange,
      test_issue     = EXCLUDED.test_issue,
      round_lot_size = EXCLUDED.round_lot_size,
      security_type  = EXCLUDED.security_type;
    """
    cur.executemany(sql, [
        (
          r["symbol"],
          r["security_name"],
          r["exchange"],
          r["test_issue"],
          r["round_lot_size"],
          r["security_type"]
        )
        for r in records
    ])
    # upsert last_updated
    cur.execute("""
    INSERT INTO last_updated (script_name,last_run)
    VALUES (%s,NOW())
    ON CONFLICT (script_name) DO UPDATE
      SET last_run = EXCLUDED.last_run;
    """, (SCRIPT_NAME,))
    conn.commit()
    cur.close()

def handler(event, context):
    logger.info("🔄 loadstocksymbols invoked")
    try:
        nas    = parse_listed(download_text_file(NASDAQ_URL), "NASDAQ")
        oth    = parse_listed(download_text_file(OTHER_URL),  "Other")
        combined = nas + oth
        deduped  = dedupe(combined)
        final    = [r for r in deduped if "$" not in r["symbol"]]
        logger.info("Deduped %d → %d", len(combined), len(final))
        insert_into_postgres(final)
        logger.info("✅ Upserted %d symbols", len(final))
        return {
            "statusCode": 200,
            "body": json.dumps({"processed": len(final)})
        }
    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "see logs"})
        }

if __name__ == "__main__":
    handler({}, None)
