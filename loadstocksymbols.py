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

# ─── Config ──────────────────────────────────────────────────────────────────────
SCRIPT_NAME   = os.path.basename(__file__)
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

# ─── Data sources & exclusion patterns ────────────────────────────────────────────
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
patterns = [
    # add any regex patterns for “other security” here
]

def get_requests_session():
    s = requests.Session()
    r = Retry(total=3, backoff_factor=1,
              status_forcelist=[429,500,502,503,504],
              allowed_methods=["GET"])
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
    # 1) drop the metadata line
    lines = [l for l in text.splitlines() if not l.startswith("File Creation Time")]
    reader = csv.DictReader(lines, delimiter="|")

    headers = reader.fieldnames or []
    # 2) pick the correct symbol column
    for cand in ("Symbol", "ACT Symbol", "NASDAQ Symbol"):
        if cand in headers:
            symbol_key = cand
            break
    else:
        raise RuntimeError(f"No symbol column in {source} file; headers={headers}")

    rows = []
    for row in reader:
        sym = row.get(symbol_key, "").strip()
        # skip empty rows & header row itself
        if not sym or sym == symbol_key:
            continue
        # skip ETFs
        if row.get("ETF", "").upper() == "Y":
            continue

        name = row.get("Security Name", "").strip()
        is_other = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)
        try:
            lot = int(row.get("Round Lot Size", "") or 0)
        except ValueError:
            lot = None

        rows.append({
            "symbol":         sym,
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue", "").strip(),
            "round_lot_size": lot,
            "security_type":  "other security" if is_other else "standard"
        })

    logger.info("Parsed %d rows from %s (using %r)", len(rows), source, symbol_key)
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
    return (_secret["username"], _secret["password"],
            _secret["host"], int(_secret["port"]), _secret["dbname"])

def _get_conn():
    global _conn
    if _conn is None:
        user,pwd,host,port,db = get_db_creds()
        logger.info("Connecting to Postgres at %s:%s/%s", host, port, db)
        _conn = psycopg2.connect(
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
    # ensure table and new column exist
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
    ALTER TABLE stock_symbols
      ADD COLUMN IF NOT EXISTS core_security VARCHAR(3);
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS last_updated (
      script_name VARCHAR(255) PRIMARY KEY,
      last_run    TIMESTAMPTZ
    );
    """)

    # upsert including core_security
    sql = """
    INSERT INTO stock_symbols
      (symbol, security_name, exchange, test_issue,
       round_lot_size, security_type, core_security)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT(symbol) DO UPDATE SET
      security_name   = EXCLUDED.security_name,
      exchange        = EXCLUDED.exchange,
      test_issue      = EXCLUDED.test_issue,
      round_lot_size  = EXCLUDED.round_lot_size,
      security_type   = EXCLUDED.security_type,
      core_security   = EXCLUDED.core_security
    ;
    """
    cur.executemany(sql, [
        (
            r["symbol"],
            r["security_name"],
            r["exchange"],
            r["test_issue"],
            r["round_lot_size"],
            r["security_type"],
            r["core_security"]
        )
        for r in records
    ])
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
        nas = parse_listed(download_text_file(NASDAQ_URL), "NASDAQ")
        oth = parse_listed(download_text_file(OTHER_URL),  "Other")
        logger.info("Parsed NASDAQ=%d, Other=%d", len(nas), len(oth))

        combined = dedupe(nas + oth)
        logger.info("Deduped to %d unique symbols", len(combined))

        # mark core_security: "yes" if retained (no "$"), else "no"
        for r in combined:
            r["core_security"] = "yes" if "$" not in r["symbol"] else "no"

        insert_into_postgres(combined)
        logger.info("✅ Upserted %d symbols", len(combined))
        return {"statusCode":200, "body":json.dumps({"processed":len(combined)})}

    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        return {"statusCode":500,"body":json.dumps({"error":"see logs"})}

if __name__=="__main__":
    handler({}, None)
