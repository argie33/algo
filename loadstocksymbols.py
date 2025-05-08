#!/usr/bin/env python3
import os
import re
import csv
import json
import logging
import requests
import boto3
import psycopg2
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

# ─── Config ──────────────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
NASDAQ_URL    = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL     = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
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

def download_text_file(url: str) -> str:
    logger.info("Downloading %s", url)
    resp = get_requests_session().get(url, timeout=(5,15))
    resp.raise_for_status()
    return resp.text

def parse_listed(text: str, source: str) -> list[dict]:
    lines = [l for l in text.splitlines() if not l.startswith("File Creation Time")]
    reader = csv.DictReader(lines, delimiter="|")
    headers = reader.fieldnames or []

    for candidate in ("Symbol", "ACT Symbol", "NASDAQ Symbol"):
        if candidate in headers:
            sym_key = candidate
            break
    else:
        raise RuntimeError(f"[{source}] No symbol column in headers {headers!r}")

    records = []
    for row in reader:
        sym = row.get(sym_key, "").strip()
        if not sym or sym == sym_key:
            logger.info("[%s] skipping header/empty row", source)
            continue
        if row.get("ETF","").upper() == "Y":
            logger.info("[%s] skipping ETF %s", source, sym)
            continue

        name = row.get("Security Name","").strip()
        is_other = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)
        try:
            lot = int(row.get("Round Lot Size","") or 0)
        except ValueError:
            lot = None

        rec = {
            "symbol": sym,
            "security_name": name,
            "exchange": source,
            "test_issue": row.get("Test Issue","").strip(),
            "round_lot_size": lot,
            "security_type": "other security" if is_other else "standard"
        }
        logger.info("[%s] parsed %s → %r", source, sym, rec)
        records.append(rec)

    logger.info("Parsed %d rows from %s (using %r)", len(records), source, sym_key)
    return records

def dedupe(records: list[dict]) -> list[dict]:
    seen = set()
    out  = []
    for r in records:
        key = (r["symbol"], r["exchange"])
        if key in seen:
            logger.info("Skipping duplicate %s[%s]", r["symbol"], r["exchange"])
        else:
            logger.info("Keeping      %s[%s]", r["symbol"], r["exchange"])
            seen.add(key)
            out.append(r)
    return out

def get_db_connection():
    sm = boto3.client("secretsmanager")
    sec = sm.get_secret_value(SecretId=DB_SECRET_ARN)
    creds = json.loads(sec["SecretString"])
    return psycopg2.connect(
        host=creds["host"],
        port=int(creds["port"]),
        dbname=creds["dbname"],
        user=creds["username"],
        password=creds["password"],
        sslmode="require"
    )

def upsert_symbols(records: list[dict]):
    conn = get_db_connection()
    with conn:
        with conn.cursor() as cur:
            # ─ Drop & recreate the main table ─────────────────────────
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

            # ─ Batch insert all rows ──────────────────────────────────
            sql = """
            INSERT INTO stock_symbols
              (symbol, security_name, exchange, test_issue,
               round_lot_size, security_type, core_security)
            VALUES (%(symbol)s, %(security_name)s, %(exchange)s,
                    %(test_issue)s, %(round_lot_size)s,
                    %(security_type)s, %(core_security)s)
            ON CONFLICT (symbol) DO UPDATE SET
              security_name  = EXCLUDED.security_name,
              exchange       = EXCLUDED.exchange,
              test_issue     = EXCLUDED.test_issue,
              round_lot_size = EXCLUDED.round_lot_size,
              security_type  = EXCLUDED.security_type,
              core_security  = EXCLUDED.core_security;
            """
            for rec in records:
                logger.info("Upserting %s[%s] core_security=%s",
                            rec["symbol"], rec["exchange"], rec["core_security"])
            execute_batch(cur, sql, records, page_size=500)

            # ─ Ensure last_updated table exists & update it ─────────
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

def handler(event=None, context=None):
    logger.info("🔄 loadstocksymbols invoked")
    try:
        nas = parse_listed(download_text_file(NASDAQ_URL), "NASDAQ")
        oth = parse_listed(download_text_file(OTHER_URL),  "Other")

        logger.info("raw counts → NASDAQ=%d, Other=%d", len(nas), len(oth))

        combined = nas + oth
        unique   = dedupe(combined)
        logger.info("after dedupe → %d total records", len(unique))

        for rec in unique:
            rec["core_security"] = "yes" if "$" not in rec["symbol"] else "no"

        upsert_symbols(unique)
        logger.info("✅ Completed upsert of %d symbols", len(unique))
        return {"statusCode":200, "body":json.dumps({"processed":len(unique)})}

    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        return {"statusCode":500, "body":json.dumps({"error":"see logs"})}

if __name__ == "__main__":
    handler()
