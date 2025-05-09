#!/usr/bin/env python3
"""
loadstocksymbols.py

Fetch NASDAQ’s listed and other-listed symbol directories via FTP,
parse & classify each row, and write **all** records into Postgres
in a table keyed by (symbol, exchange).
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
OTHER_PATTERNS = patterns = [
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

def fetch_text_ftp(filename: str) -> str:
    """Download a file via FTP and return its contents."""
    logger.info("Connecting to FTP %s to fetch %s", FTP_HOST, filename)
    ftp = FTP(FTP_HOST)
    ftp.login()
    ftp.cwd(FTP_DIR)
    lines: list[str] = []
    ftp.retrlines(f"RETR {filename}", lines.append)
    ftp.quit()
    return "\n".join(lines)

def parse_listed(text: str, source: str) -> list[dict]:
    """
    Parse a pipe-delimited listing:
      - Find the header row (contains "Security Name"|...)
      - Use csv.DictReader on the remainder
      - Pick "Symbol" or "NASDAQ Symbol"
      - Classify as 'etf', 'other security', or 'standard'
    """
    lines = text.splitlines()
    header_idx = next((i for i, L in enumerate(lines)
                       if "Security Name" in L and "|" in L), None)
    if header_idx is None:
        logger.error("[%s] header row not found", source)
        return []

    reader = csv.DictReader(lines[header_idx:], delimiter="|")
    headers = reader.fieldnames or []

    # choose symbol column
    for cand in ("Symbol", "NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        logger.error("[%s] no Symbol column", source)
        return []

    out: list[dict] = []
    for row in reader:
        sym = (row.get(sym_key) or "").strip()
        if not sym:
            continue

        name = (row.get("Security Name") or "").strip()
        # round lot
        try:
            lot = int((row.get("Round Lot Size") or "").strip() or 0)
        except ValueError:
            lot = None

        # ETF flag (Y/N)
        is_etf = (row.get("ETF") or "").strip().upper() == "Y"
        # other‑security via regex
        is_other = any(re.search(p, name, flags=re.IGNORECASE)
                       for p in OTHER_PATTERNS)

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

    logger.info("[%s] parsed %d rows", source, len(out))
    return out

def get_db_connection():
    """Fetch DB creds from Secrets Manager and return a psycopg2 connection."""
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

def main():
    # 1) fetch & parse every source
    all_records: list[dict] = []
    for src, fname in FTP_FILES.items():
        text = fetch_text_ftp(fname)
        rows = parse_listed(text, src)
        all_records.extend(rows)

    # 2) flag core_security
    for r in all_records:
        r["core_security"] = "yes" if "$" not in r["symbol"] else "no"

    # 3) write to DB
    conn = get_db_connection()
    cur = conn.cursor()

    # drop & recreate with composite primary key
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

    insert_sql = """
    INSERT INTO stock_symbols
      (symbol, exchange, security_name, test_issue, round_lot_size, security_type, core_security)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    ;
    """
    cur.executemany(insert_sql, [
        (
            r["symbol"],
            r["exchange"],
            r["security_name"],
            r["test_issue"],
            r["round_lot_size"],
            r["security_type"],
            r["core_security"]
        ) for r in all_records
    ])
    conn.commit()
    conn.close()

    logger.info("✅ Wrote %d rows to stock_symbols", len(all_records))

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("❌ loadstocksymbols failed")
        raise
