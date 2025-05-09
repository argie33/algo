#!/usr/bin/env python3
import os
import re
import csv
import json
import logging
from ftplib import FTP
import boto3
import psycopg2

# ─── Logging setup ───────────────────────────────────────────────────────────────
logger = logging.getLogger("loadstocksymbols")
logger.setLevel(logging.INFO)
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(h)

# ─── Configuration ───────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]
FTP_HOST      = "ftp.nasdaqtrader.com"
FTP_DIR       = "symboldirectory"
FTP_FILE      = "otherlisted.txt"

# any regexes for classifying “other security”:
patterns = [
    # e.g. r"\bpreferred\b", r"\bredeem\b"
]

def fetch_text_ftp() -> str:
    """Download the otherlisted.txt file via FTP and return its body."""
    logger.info("Connecting to FTP %s", FTP_HOST)
    ftp = FTP(FTP_HOST)
    ftp.login()
    ftp.cwd(FTP_DIR)
    lines = []
    ftp.retrlines(f"RETR {FTP_FILE}", lines.append)
    ftp.quit()
    text = "\n".join(lines)
    logger.info("Downloaded %s from FTP", FTP_FILE)
    return text

def parse_listed(text: str, source: str) -> list[dict]:
    """
    Parse a pipe‑delimited listing:
    - Find the real header row (contains "Security Name" + pipe)
    - Use that header for csv.DictReader
    - Dynamically pick Symbol or NASDAQ Symbol (no ACT Symbol)
    """
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if "Security Name" in line and "|" in line:
            header_idx = i
            break
    if header_idx is None:
        logger.error("[%s] could not find header row", source)
        return []

    reader = csv.DictReader(lines[header_idx:], delimiter="|")
    headers = reader.fieldnames or []

    # pick only "Symbol" or "NASDAQ Symbol"
    for cand in ("Symbol", "NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        logger.error("[%s] no Symbol column in headers %s", source, headers)
        return []

    records = []
    for row in reader:
        # guard against None from row.get(...)
        raw_sym = row.get(sym_key) or ""
        sym = raw_sym.strip()
        if not sym:
            # skip blank or malformed rows
            continue

        raw_name = row.get("Security Name") or ""
        name = raw_name.strip()
        try:
            lot = int((row.get("Round Lot Size") or "").strip() or 0)
        except ValueError:
            lot = None

        is_other = any(
            re.search(p, name, flags=re.IGNORECASE) for p in patterns
        )

        records.append({
            "symbol":         sym,
            "security_name":  name,
            "exchange":       source,
            "test_issue":     (row.get("Test Issue") or "").strip(),
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
    # ── Fetch & parse only the FTP‐sourced list ─────────────────────────────────
    oth_text = fetch_text_ftp()
    oth = parse_listed(oth_text, "Other")
    logger.info("Raw counts → Other=%d", len(oth))

    # ── Dedupe on (symbol,exchange) ────────────────────────────────────────────
    seen   = set()
    unique = []
    for rec in oth:
        key = (rec["symbol"], rec["exchange"])
        if key not in seen:
            seen.add(key)
            unique.append(rec)
    logger.info("After dedupe → %d unique records", len(unique))

    # ── Flag core_security & attach to each record ────────────────────────────
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
        VALUES (%s,%s,%s,%s,%s,%s,%s);
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
