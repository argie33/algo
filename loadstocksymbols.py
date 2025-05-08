#!/usr/bin/env python3
import os
import re
import csv
import json
import logging
import requests
import boto3
import psycopg2
import urllib.request

from psycopg2.extras import execute_batch
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
NASDAQ_URL    = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_FTP_URL = "ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt"
# any patterns that make a name “other security” rather than “standard”
patterns = [
   r"\bpreferred\b",
    r"\bredeemable warrant(s)?\b",
    r"\bwarrant(s)?\b",
    r"\bunit(s)?\b",
    r"\bsubordinated\b",
    r"\bperpetual subordinated notes\b",
    r"\bconvertible\b",
    r"\bsenior note(s)?\b",
    r"\bcapital investments\b",
    r"\bnotes due\b",
    r"\bincome trust\b",
    r"\blimited partnership units\b",
    r"\bsubordinate\b",
    r"\s*-\s*(one\s+)?right(s)?\b",
    r"\bclosed end fund\b",
    r"\bpreferred securities\b",
    r"\bnon-cumulative\b",
    r"\bredeemable preferred\b",
    r"\bpreferred class\b",
    r"\bpreferred share(s)?\b",
    r"\betns\b",
    r"\bFixed-to-Floating Rate\b",
    r"\bseries d\b",
    r"\bseries b\b",
    r"\bseries f\b",
    r"\bseries h\b",
    r"\bperpetual preferred\b",
    r"\bincome fund\b",
    r"\bfltg rate\b",
    r"\bclass c-1\b",
    r"\bbeneficial interest\b",
    r"\bfund\b",
    r"\bcapital obligation notes\b",
    r"\bfixed rate\b",
    r"\bdep shs\b",
    r"\bopportunities trust\b",
    r"\bnyse tick pilot test\b",
    r"\bpreference share\b",
    r"\bseries g\b",
    r"\bfutures etn\b",
    r"\btrust for\b",
    r"\btest stock\b",
    r"\bnastdaq symbology test\b",
    r"\biex test\b",
    r"\bnasdaq test\b",
    r"\bnyse arca test\b",
    r"\bpreference\b",
    r"\bredeemable\b",
    r"\bperpetual preference\b",
    r"\btax free income\b",
    r"\bstructured products\b",
    r"\bcorporate backed trust\b",
    r"\bfloating rate\b",
    r"\btrust securities\b",
    r"\bfixed-income\b",
    r"\bpfd ser\b",
    r"\bpfd\b",
    r"\bmortgage bonds\b",
    r"\bmortgage capital\b",
    r"\bseries due\b",
    r"\btarget term\b",
    r"\bterm trust\b",
    r"\bperpetual conv\b",
    r"\bmunicipal bond\b",
    r"\bdigitalbridge group\b",
    r"\bnyse test\b",
    r"\bctest\b",
    r"\btick pilot test\b",
    r"\bexchange test\b",
    r"\bbats bzx\b",
    r"\bdividend trust\b",
    r"\bbond trust\b",
    r"\bmunicipal trust\b",
    r"\bmortgage trust\b",
    r"\btrust etf\b",
    r"\bcapital trust\b",
    r"\bopportunity trust\b",
    r"\binvestors trust\b",
    r"\bincome securities trust\b",
    r"\bresources trust\b",
    r"\benergy trust\b",
    r"\bsciences trust\b",
    r"\bequity trust\b",
    r"\bmulti-media trust\b",
    r"\bmedia trust\b",
    r"\bmicro-cap trust\b",
    r"\bmicro-cap\b",
    r"\bsmall-cap trust\b",
    r"\bglobal trust\b",
    r"\bsmall-cap\b",
    r"\bsce trust\b",
    r"\bacquisition\b",
    r"\bcontingent\b",
    r"\bii inc\b",
    r"\bnasdaq symbology\b",
    r"\bsymbology\b", 
]

def get_requests_session():
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

def download_text_http(url: str) -> str:
    logger.info("Downloading (HTTP) %s", url)
    resp = get_requests_session().get(url, timeout=(5,15))
    resp.raise_for_status()
    return resp.text

def download_text_ftp(url: str) -> str:
    logger.info("Downloading (FTP) %s", url)
    with urllib.request.urlopen(url) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def parse_listed(text: str, source: str) -> list[dict]:
    # drop any “File Creation Time” lines
    lines = [L for L in text.splitlines() if not L.startswith("File Creation Time")]
    reader = csv.DictReader(lines, delimiter="|")
    headers = reader.fieldnames or []
    # pick whichever symbol-column they sent us
    symbol_key = next((c for c in ("Symbol","ACT Symbol","NASDAQ Symbol") if c in headers), None)
    if not symbol_key:
        raise RuntimeError(f"[{source}] no symbol column in headers {headers!r}")

    out = []
    for row in reader:
        sym = row.get(symbol_key,"").strip()
        # skip blank rows & the header-row itself
        if not sym or sym == symbol_key:
            continue
        # drop ETFs
        if row.get("ETF","").upper()=="Y":
            continue

        name     = row.get("Security Name","").strip()
        is_other = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)
        try:
            lot = int(row.get("Round Lot Size","") or 0)
        except ValueError:
            lot = None

        out.append({
            "symbol":         sym,
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue","").strip(),
            "round_lot_size": lot,
            "security_type":  "other security" if is_other else "standard"
        })

    logger.info("Parsed %d rows from %s", len(out), source)
    return out

def get_db_connection():
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

def handler(event=None, context=None):
    logger.info("🔄 loadstocksymbols invoked")
    try:
        # ── fetch & parse ─────────────────────────────────────────────
        nas_text = download_text_http(NASDAQ_URL)
        oth_text = download_text_ftp(OTHER_FTP_URL)

        nas = parse_listed(nas_text, "NASDAQ")
        oth = parse_listed(oth_text,  "Other")
        logger.info("Counts → NASDAQ=%d, Other=%d", len(nas), len(oth))

        # ── dedupe on (symbol,exchange) ───────────────────────────────
        seen   = set()
        unique = []
        for rec in nas + oth:
            key = (rec["symbol"], rec["exchange"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(rec)
        logger.info("After dedupe → %d unique rows", len(unique))

        # ── flag core_security ────────────────────────────────────────
        for rec in unique:
            rec["core_security"] = "yes" if "$" not in rec["symbol"] else "no"

        # ── write to PostgreSQL ────────────────────────────────────────
        conn = get_db_connection()
        with conn:
            cur = conn.cursor()
            # drop & recreate
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
            # batch upsert (here effectively just inserts, since we just dropped)
            sql = """
            INSERT INTO stock_symbols
              (symbol, security_name, exchange, test_issue,
               round_lot_size, security_type, core_security)
            VALUES (
              %(symbol)s, %(security_name)s, %(exchange)s, %(test_issue)s,
              %(round_lot_size)s, %(security_type)s, %(core_security)s
            )
            ON CONFLICT(symbol) DO UPDATE SET
              security_name  = EXCLUDED.security_name,
              exchange       = EXCLUDED.exchange,
              test_issue     = EXCLUDED.test_issue,
              round_lot_size = EXCLUDED.round_lot_size,
              security_type  = EXCLUDED.security_type,
              core_security  = EXCLUDED.core_security;
            """
            execute_batch(cur, sql, unique, page_size=500)

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

        logger.info("✅ Completed upsert of %d symbols", len(unique))
        return {"statusCode":200, "body":json.dumps({"processed":len(unique)})}

    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        return {"statusCode":500, "body":json.dumps({"error":"see logs"})}

if __name__ == "__main__":
    handler()
