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
FTP_FILES     = {
    "NASDAQ": "nasdaqlisted.txt",
    "Other":  "otherlisted.txt"
}

# any regexes for classifying “other security”:
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
    ]

def fetch_text_ftp(filename: str) -> str:
    """Download the given file via FTP and return its full text."""
    logger.info("Connecting to FTP %s", FTP_HOST)
    ftp = FTP(FTP_HOST)
    ftp.login()
    ftp.cwd(FTP_DIR)

    lines: list[str] = []
    ftp.retrlines(f"RETR {filename}", lines.append)
    ftp.quit()

    text = "\n".join(lines)
    logger.info("Downloaded %s from FTP", filename)
    return text

def parse_listed(text: str, source: str) -> list[dict]:
    """
    Parse a pipe‑delimited listing:
    - Find the real header row (contains "Security Name" + pipe)
    - Use that for csv.DictReader
    - Dynamically pick only Symbol or NASDAQ Symbol (no ACT Symbol)
    - Classify each row as 'etf', 'other security', or 'standard'
    """
    lines = text.splitlines()
    header_idx = next((i for i, L in enumerate(lines)
                       if "Security Name" in L and "|" in L), None)
    if header_idx is None:
        logger.error("[%s] could not find header row", source)
        return []

    reader = csv.DictReader(lines[header_idx:], delimiter="|")
    headers = reader.fieldnames or []

    # only consider "Symbol" or "NASDAQ Symbol"
    for cand in ("Symbol", "NASDAQ Symbol"):
        if cand in headers:
            sym_key = cand
            break
    else:
        logger.error("[%s] no Symbol column in headers %s", source, headers)
        return []

    records: list[dict] = []
    for row in reader:
        sym = (row.get(sym_key) or "").strip()
        if not sym:
            continue  # skip blanks

        name = (row.get("Security Name") or "").strip()
        try:
            lot = int((row.get("Round Lot Size") or "").strip() or 0)
        except ValueError:
            lot = None

        # ETF flag in source file ('Y' or 'N')
        is_etf = (row.get("ETF") or "").strip().upper() == "Y"
        # other‐security regex match
        is_other = any(re.search(p, name, flags=re.IGNORECASE)
                       for p in patterns)

        if is_etf:
            sec_type = "etf"
        else:
            sec_type = "other security" if is_other else "standard"

        records.append({
            "symbol":         sym,
            "security_name":  name,
            "exchange":       source,
            "test_issue":     (row.get("Test Issue") or "").strip(),
            "round_lot_size": lot,
            "security_type":  sec_type
        })

    logger.info("[%s] Parsed %d rows", source, len(records))
    return records

def get_db_connection():
    """Retrieve DB credentials from Secrets Manager and return a psycopg2 connection."""
    sec = boto3.client("secretsmanager").get_secret_value(SecretId=DB_SECRET_ARN)
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
    # ── Fetch & parse both FTP files ────────────────────────────────────────────
    all_records = []
    for source, fname in FTP_FILES.items():
        raw = fetch_text_ftp(fname)
        parsed = parse_listed(raw, source)
        all_records.extend(parsed)
    logger.info("Raw total rows → %d", len(all_records))

    # ── Dedupe on (symbol,exchange) ────────────────────────────────────────────
    seen, unique = set(), []
    for rec in all_records:
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
