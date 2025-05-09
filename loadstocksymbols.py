#!/usr/bin/env python3
import os
import sys
import re
import csv
import logging
from ftplib import FTP
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ───────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols")

# ─── Environment for PostgreSQL RDS ─────────────────────────────────────────────
POSTGRES_HOST     = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB       = os.environ.get("POSTGRES_DB", "stocks")
POSTGRES_USER     = os.environ.get("POSTGRES_USER", "stocks")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "bed0elAn")

SCRIPT_NAME = os.path.basename(__file__)

# ─── FTP configuration ──────────────────────────────────────────────────────────
FTP_HOST = "ftp.nasdaqtrader.com"
FTP_DIR  = "symboldirectory"
FTP_FILES = {
    "NASDAQ": "nasdaqlisted.txt",
    "OTHER":  "otherlisted.txt"
}

# ─── Regex Patterns for Filtering Out Unwanted Securities ───────────────────────
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

def should_filter(name, patterns):
    for pat in patterns:
        if re.search(pat, name, flags=re.IGNORECASE):
            return True
    return False

excluded_records = []

def download_ftp_file(filename):
    logger.info(f"Connecting to FTP {FTP_HOST}")
    ftp = FTP(FTP_HOST, timeout=30)
    ftp.login()  # anonymous
    ftp.cwd(FTP_DIR)
    logger.info(f"Retrieving {filename}")
    lines = []
    ftp.retrlines(f"RETR {filename}", callback=lines.append)
    ftp.quit()
    return "\n".join(lines)

def parse_nasdaq_listed(text):
    logger.info("Parsing NASDAQ-listed records")
    recs = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row["Symbol"].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        if row["ETF"].upper()=="Y" or should_filter(name, patterns):
            excluded_records.append({
                "source":"NASDAQ",
                "symbol": row["Symbol"].strip(),
                "security_name": name
            })
            continue
        try:
            lot = int(row["Round Lot Size"])
        except:
            lot = None
        recs.append({
            "symbol": row["Symbol"].strip(),
            "security_name": name,
            "exchange": "NASDAQ",
            "cqs_symbol": None,
            "market_category": row["Market Category"].strip(),
            "test_issue": row["Test Issue"].strip(),
            "financial_status": row["Financial Status"].strip(),
            "round_lot_size": lot,
            "etf": row["ETF"].strip(),
            "secondary_symbol": row["NextShares"].strip()
        })
    return recs

def parse_other_listed(text):
    logger.info("Parsing Other-listed records")
    recs = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    exch_map = {"A":"American Stock Exchange","N":"New York Stock Exchange",
                "P":"NYSE Arca","Z":"BATS Global Markets"}
    for row in reader:
        if row["ACT Symbol"].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        if row["ETF"].upper()=="Y" or should_filter(name, patterns):
            excluded_records.append({
                "source":"Other",
                "symbol": row["ACT Symbol"].strip(),
                "security_name": name
            })
            continue
        try:
            lot = int(row["Round Lot Size"])
        except:
            lot = None
        exch = exch_map.get(row["Exchange"].strip(), row["Exchange"].strip())
        recs.append({
            "symbol": row["ACT Symbol"].strip(),
            "security_name": name,
            "exchange": exch,
            "cqs_symbol": row["CQS Symbol"].strip(),
            "market_category": None,
            "test_issue": row["Test Issue"].strip(),
            "financial_status": None,
            "round_lot_size": lot,
            "etf": row["ETF"].strip(),
            "secondary_symbol": row["NASDAQ Symbol"].strip()
        })
    return recs

def deduplicate_records(records):
    logger.info("Deduplicating records")
    unique = {}
    for r in records:
        if r["symbol"] not in unique:
            unique[r["symbol"]] = r
    return list(unique.values())

def insert_into_postgres(records):
    logger.info("Connecting to PostgreSQL")
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    create_sql = """
    CREATE TABLE IF NOT EXISTS stock_symbols (
      symbol TEXT PRIMARY KEY,
      security_name TEXT,
      exchange TEXT,
      cqs_symbol TEXT,
      market_category TEXT,
      test_issue CHAR(1),
      financial_status TEXT,
      round_lot_size INT,
      etf CHAR(1),
      secondary_symbol TEXT
    );
    """
    insert_sql = """
    INSERT INTO stock_symbols (
      symbol, security_name, exchange, cqs_symbol,
      market_category, test_issue, financial_status,
      round_lot_size, etf, secondary_symbol
    ) VALUES %s
    ON CONFLICT (symbol) DO UPDATE SET
      security_name = EXCLUDED.security_name,
      exchange = EXCLUDED.exchange,
      cqs_symbol = EXCLUDED.cqs_symbol,
      market_category = EXCLUDED.market_category,
      test_issue = EXCLUDED.test_issue,
      financial_status = EXCLUDED.financial_status,
      round_lot_size = EXCLUDED.round_lot_size,
      etf = EXCLUDED.etf,
      secondary_symbol = EXCLUDED.secondary_symbol;
    """
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(create_sql)
                vals = [
                    (
                      r["symbol"], r["security_name"], r["exchange"],
                      r["cqs_symbol"], r["market_category"], r["test_issue"],
                      r["financial_status"], r["round_lot_size"],
                      r["etf"], r["secondary_symbol"]
                    )
                    for r in records
                ]
                logger.info(f"Inserting {len(vals)} records")
                execute_values(cur, insert_sql, vals, page_size=500)
    except Exception:
        logger.exception("Failed to insert into PostgreSQL")
        raise
    finally:
        conn.close()

def update_last_updated():
    logger.info("Updating last_updated table")
    conn = psycopg2.connect(
        host=POSTGRES_HOST, port=POSTGRES_PORT,
        dbname=POSTGRES_DB, user=POSTGRES_USER,
        password=POSTGRES_PASSWORD
    )
    sql = """
    CREATE TABLE IF NOT EXISTS last_updated (
      script_name TEXT PRIMARY KEY,
      last_updated TIMESTAMPTZ
    );
    INSERT INTO last_updated (script_name, last_updated)
    VALUES (%s, NOW())
    ON CONFLICT (script_name) DO UPDATE
      SET last_updated = EXCLUDED.last_updated;
    """
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql, (SCRIPT_NAME,))
    except Exception:
        logger.exception("Failed to update last_updated")
    finally:
        conn.close()

def write_excluded_csv(fn="excluded_records.csv"):
    if not excluded_records:
        logger.info("No excluded records")
        return
    with open(fn, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source","symbol","security_name"])
        writer.writeheader()
        writer.writerows(excluded_records)
    logger.info(f"Wrote {fn}")

def write_included_csv(records, fn="included_records.csv"):
    if not records:
        logger.info("No included records")
        return
    with open(fn, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    logger.info(f"Wrote {fn}")

def main():
    texts = {}
    for source, fname in FTP_FILES.items():
        texts[source] = download_ftp_file(fname)

    nasdaq_recs = parse_nasdaq_listed(texts["NASDAQ"])
    other_recs  = parse_other_listed(texts["OTHER"])

    all_recs = nasdaq_recs + other_recs
    logger.info(f"Before dedupe: {len(all_recs)}")
    unique_recs = deduplicate_records(all_recs)
    logger.info(f"After dedupe: {len(unique_recs)}")

    filtered = []
    for r in unique_recs:
        if "$" in r["symbol"]:
            excluded_records.append({"source":"DollarFilter",
                                     "symbol":r["symbol"],
                                     "security_name":r["security_name"]})
        else:
            filtered.append(r)
    logger.info(f"After $-filter: {len(filtered)}")

    insert_into_postgres(filtered)
    write_excluded_csv()
    write_included_csv(filtered)
    update_last_updated()
    logger.info("Complete")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Unhandled exception")
        sys.exit(1)
