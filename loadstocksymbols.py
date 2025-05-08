#!/usr/bin/env python3
import os
import re
import csv
import json
import logging
from ftplib import FTP
import boto3
import psycopg2
from psycopg2.extras import execute_batch

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger("loadstocksymbols")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)

# ─── Configuration ───────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
NASDAQ_FTP    = "nasdaqlisted.txt"
OTHER_FTP     = "otherlisted.txt"
FTP_HOST      = "ftp.nasdaqtrader.com"
patterns = [
    # add any regex patterns for “other security” classification here
]

def download_listed_ftp(filename: str) -> str:
    """
    Connects to the Nasdaq FTP site, retrieves the given filename,
    and returns its contents as a UTF-8 string.
    """
    ftp = FTP(FTP_HOST)
    ftp.login()
    # try both common directory names
    for dir_name in ("SymDir","symboldirectory"):
        try:
            ftp.cwd(dir_name)
            break
        except Exception:
            continue
    else:
        raise RuntimeError(f"Could not find SymDir on {FTP_HOST}")

    lines = []
    ftp.retrlines(f"RETR {filename}", callback=lines.append)
    ftp.quit()
    return "\n".join(lines)

def parse_listed(text: str, source: str) -> list[dict]:
    """
    Parses a Nasdaq pipe‐delimited “listed” file into records.
    Dynamically picks the symbol column, skips metadata/header,
    filters out ETFs, and classifies security_type.
    """
    # drop any “File Creation Time” metadata lines
    rows = [L for L in text.splitlines() if not L.startswith("File Creation Time")]
    reader = csv.DictReader(rows, delimiter="|")
    headers = reader.fieldnames or []

    # pick the symbol column
    for cand in ("Symbol","ACT Symbol","NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        raise RuntimeError(f"[{source}] no symbol column in headers {headers!r}")

    out = []
    for row in reader:
        sym = row.get(sym_key, "").strip()
        # skip blank rows & the header‐row itself
        if not sym or sym == sym_key:
            continue
        # skip ETFs
        if row.get("ETF","").upper() == "Y":
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
        # ── Download & parse both lists ───────────────────────────────────────
        nas_text = download_listed_ftp(NASDAQ_FTP)
        oth_text = download_listed_ftp(OTHER_FTP)

        nas = parse_listed(nas_text, "NASDAQ")
        oth = parse_listed(oth_text,  "Other")
        logger.info("Counts → NASDAQ=%d, Other=%d", len(nas), len(oth))

        # ── Dedupe on (symbol,exchange) ─────────────────────────────────────
        seen   = set()
        unique = []
        for rec in nas + oth:
            key = (rec["symbol"], rec["exchange"])
            if key not in seen:
                seen.add(key)
                unique.append(rec)
        logger.info("After dedupe → %d unique rows", len(unique))

        # ── Flag core_security & attach source_file ──────────────────────────
        for rec in unique:
            rec["core_security"] = "yes" if "$" not in rec["symbol"] else "no"
            rec["source_file"]   = rec["exchange"]  # or the FTP filename if you prefer

        # ── Write to PostgreSQL ──────────────────────────────────────────────
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
              core_security   CHAR(3),
              source_file     TEXT
            );
            """)
            # batch insert
            sql = """
            INSERT INTO stock_symbols
              (symbol, security_name, exchange, test_issue,
               round_lot_size, security_type, core_security, source_file)
            VALUES (
              %(symbol)s, %(security_name)s, %(exchange)s, %(test_issue)s,
              %(round_lot_size)s, %(security_type)s, %(core_security)s, %(source_file)s
            )
            ON CONFLICT(symbol) DO UPDATE SET
              security_name  = EXCLUDED.security_name,
              exchange       = EXCLUDED.exchange,
              test_issue     = EXCLUDED.test_issue,
              round_lot_size = EXCLUDED.round_lot_size,
              security_type  = EXCLUDED.security_type,
              core_security  = EXCLUDED.core_security,
              source_file    = EXCLUDED.source_file;
            """
            execute_batch(cur, sql, unique, page_size=500)

            # last_updated table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS last_updated (
              script_name VARCHAR(255) PRIMARY KEY,
              last_run    TIMESTAMPTZ
            );
            """)
            cur.execute("""
            INSERT INTO last_updated (script_name,last_run)
            VALUES (%s,NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
            """, (os.path.basename(__file__),))
        conn.close()

        logger.info("✅ Completed upsert of %d symbols", len(unique))
        return {"statusCode":200, "body":json.dumps({"processed":len(unique)})}

    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        return {"statusCode":500,"body":json.dumps({"error":"see logs"})}

if __name__ == "__main__":
    handler()
