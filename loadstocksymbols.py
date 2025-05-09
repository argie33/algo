#!/usr/bin/env python3
"""
loadstocksymbols.py

Job 0) init: Drop & recreate the target table.
Job 1) Other:   Fetch/parse otherlisted.txt → insert.
Job 2) NASDAQ: Fetch/parse nasdaqlisted.txt → insert.
"""

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
FTP_FILES     = {
    "Other":  "otherlisted.txt",
    "NASDAQ": "nasdaqlisted.txt"
}

# regexes for classifying “other security”
OTHER_PATTERNS = [
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
    ]

def get_db_connection():
    """Job helper: open a new Postgres connection."""
    sec = boto3.client("secretsmanager").get_secret_value(SecretId=DB_SECRET_ARN)
    cfg = json.loads(sec["SecretString"])
    return psycopg2.connect(
        host     = cfg["host"],
        port     = int(cfg["port"]),
        dbname   = cfg["dbname"],
        user     = cfg["username"],
        password = cfg["password"],
        sslmode  = "require"
    )

def fetch_text_ftp(filename: str) -> str:
    """Job helper: fetch a file from the FTP server."""
    logger.info("Fetching %s", filename)
    ftp = FTP(FTP_HOST)
    ftp.login()
    ftp.cwd(FTP_DIR)
    lines = []
    ftp.retrlines(f"RETR {filename}", lines.append)
    ftp.quit()
    return "\n".join(lines)

def parse_listed(text: str, source: str) -> list[dict]:
    """Job helper: parse the pipe-delimited listing into records."""
    lines = text.splitlines()
    idx = next((i for i, L in enumerate(lines) if "Security Name" in L and "|" in L), None)
    if idx is None:
        logger.error("[%s] no header", source)
        return []

    reader = csv.DictReader(lines[idx:], delimiter="|")
    headers = reader.fieldnames or []
    # pick symbol column
    for cand in ("Symbol", "NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        logger.error("[%s] no Symbol column", source)
        return []

    out = []
    for row in reader:
        sym = (row.get(sym_key) or "").strip()
        if not sym:
            continue

        name = (row.get("Security Name") or "").strip()
        try:
            lot = int((row.get("Round Lot Size") or "").strip() or 0)
        except ValueError:
            lot = None

        is_etf   = (row.get("ETF") or "").strip().upper() == "Y"
        is_other = any(re.search(p, name, flags=re.IGNORECASE) for p in OTHER_PATTERNS)

        if is_etf:
            sec_type = "etf"
        elif is_other:
            sec_type = "other security"
        else:
            sec_type = "standard"

        out.append({
            "symbol":         sym,
            "exchange":       source,
            "security_name":  name,
            "test_issue":     (row.get("Test Issue") or "").strip(),
            "round_lot_size": lot,
            "security_type":  sec_type
        })
    logger.info("[%s] parsed %d", source, len(out))
    return out

def job_init():
    """Job 0: Drop & recreate the target table."""
    logger.info("Job 0: init – recreate table")
    conn = get_db_connection()
    with conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS stock_symbols;")
        cur.execute("""
            CREATE TABLE stock_symbols (
              symbol          VARCHAR(50),
              exchange        VARCHAR(20),
              security_name   TEXT,
              test_issue      CHAR(1),
              round_lot_size  INT,
              security_type   VARCHAR(20),
              core_security   CHAR(3),
              PRIMARY KEY (symbol, exchange)
            );
        """)
        conn.commit()
    conn.close()

def job_insert(source: str, filename: str):
    """
    Job 1 & 2: fetch → parse → insert for one source.
    Runs in its own DB connection.
    """
    logger.info("Job insert: %s", source)
    text    = fetch_text_ftp(filename)
    records = parse_listed(text, source)
    if not records:
        logger.warning("No records for %s, skipping insert", source)
        return

    # flag core_security
    for r in records:
        r["core_security"] = "yes" if "$" not in r["symbol"] else "no"

    conn = get_db_connection()
    with conn:
        cur = conn.cursor()
        cur.executemany("""
            INSERT INTO stock_symbols
              (symbol, exchange, security_name, test_issue, round_lot_size, security_type, core_security)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (symbol, exchange) DO NOTHING;
        """, [
            (
                r["symbol"],
                r["exchange"],
                r["security_name"],
                r["test_issue"],
                r["round_lot_size"],
                r["security_type"],
                r["core_security"]
            ) for r in records
        ])
        conn.commit()
    conn.close()
    logger.info("Inserted %d rows for %s", len(records), source)

def main():
    try:
        job_init()
        # run Job 1 then Job 2, serially
        job_insert("Other",  FTP_FILES["Other"])
        job_insert("NASDAQ", FTP_FILES["NASDAQ"])
        logger.info("✅ All jobs complete")
    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        raise

if __name__ == "__main__":
    main()
