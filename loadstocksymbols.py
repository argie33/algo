#!/usr/bin/env python3
import os
import re
import csv
import json
import sys
import logging
import requests
import boto3
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ─────────────────────────────────────────────────────────────
# Attach a StreamHandler to root so all logger.info/debug/warning go to stdout.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols")

# ─── Postgres via Secrets Manager ─────────────────────────────────────────────
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("Environment variable DB_SECRET_ARN is not set")
    sys.exit(1)

def get_db_config():
    logger.info("Fetching DB credentials from Secrets Manager")
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    secret = json.loads(resp["SecretString"])
    return (
        secret["host"],
        secret.get("port", "5432"),
        secret["username"],
        secret["password"],
        secret["dbname"]
    )

PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB = get_db_config()

# ─── Data Source URLs ────────────────────────────────────────────────────────
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# ─── Filtering Patterns ───────────────────────────────────────────────────────
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

def should_filter(name: str) -> bool:
    for p in patterns:
        if re.search(p, name, flags=re.IGNORECASE):
            return True
    return False

# ─── Parsers ─────────────────────────────────────────────────────────────────
def parse_nasdaq_listed(text: str):
    recs = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if not row.get("Symbol") or row["Symbol"].startswith("File Creation Time"):
            continue
        name = row.get("Security Name", "").strip()
        if row.get("ETF", "").upper() == "Y" or should_filter(name):
            continue
        try:
            lot = int(row.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        recs.append({
            "symbol":           row["Symbol"].strip(),
            "security_name":    name,
            "exchange":         "NASDAQ",
            "cqs_symbol":       None,
            "market_category":  row.get("Market Category", "").strip(),
            "test_issue":       row.get("Test Issue", "").strip(),
            "financial_status": row.get("Financial Status", "").strip(),
            "round_lot_size":   lot,
            "etf":              row.get("ETF", "").strip(),
            "secondary_symbol": row.get("NextShares", "").strip(),
        })
    return recs

def parse_other_listed(text: str):
    recs = []
    exch_map = {"A": "American Stock Exchange",
                "N": "New York Stock Exchange",
                "P": "NYSE Arca",
                "Z": "BATS Global Markets"}
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if not row.get("ACT Symbol") or row["ACT Symbol"].startswith("File Creation Time"):
            continue
        name = row.get("Security Name", "").strip()
        if row.get("ETF", "").upper() == "Y" or should_filter(name):
            continue
        try:
            lot = int(row.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        recs.append({
            "symbol":           row["ACT Symbol"].strip(),
            "security_name":    name,
            "exchange":         exch_map.get(row.get("Exchange"), row.get("Exchange","")),
            "cqs_symbol":       row.get("CQS Symbol","").strip(),
            "market_category":  None,
            "test_issue":       row.get("Test Issue","").strip(),
            "financial_status": None,
            "round_lot_size":   lot,
            "etf":              row.get("ETF","").strip(),
            "secondary_symbol": row.get("NASDAQ Symbol","").strip(),
        })
    return recs

def choose_parser(text: str):
    headers = csv.DictReader(text.splitlines(), delimiter="|").fieldnames or []
    if "Symbol" in headers:
        return parse_nasdaq_listed
    if "ACT Symbol" in headers:
        return parse_other_listed
    raise RuntimeError(f"Unknown format, headers: {headers}")

# ─── DB Utilities ────────────────────────────────────────────────────────────
def init_db_schema(conn):
    logger.info("Initializing DB schema")
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS stock_symbols;")
        cur.execute("""
            CREATE TABLE stock_symbols (
                symbol            VARCHAR(50) PRIMARY KEY,
                security_name     TEXT,
                exchange          VARCHAR(100),
                cqs_symbol        VARCHAR(50),
                market_category   VARCHAR(50),
                test_issue        CHAR(1),
                financial_status  VARCHAR(50),
                round_lot_size    INT,
                etf               CHAR(1),
                secondary_symbol  VARCHAR(50)
            );
        """)
        cur.execute("DROP TABLE IF EXISTS last_updated;")
        cur.execute("""
            CREATE TABLE last_updated (
                script_name   VARCHAR(255) PRIMARY KEY,
                last_run      TIMESTAMP WITH TIME ZONE
            );
        """)
    conn.commit()

def insert_records(conn, records):
    logger.info("Inserting/updating %d records", len(records))
    sql = """
      INSERT INTO stock_symbols (
        symbol, security_name, exchange, cqs_symbol,
        market_category, test_issue, financial_status,
        round_lot_size, etf, secondary_symbol
      ) VALUES %s
      ON CONFLICT (symbol) DO UPDATE SET
        security_name    = EXCLUDED.security_name,
        exchange         = EXCLUDED.exchange,
        cqs_symbol       = EXCLUDED.cqs_symbol,
        market_category  = EXCLUDED.market_category,
        test_issue       = EXCLUDED.test_issue,
        financial_status = EXCLUDED.financial_status,
        round_lot_size   = EXCLUDED.round_lot_size,
        etf              = EXCLUDED.etf,
        secondary_symbol = EXCLUDED.secondary_symbol;
    """
    vals = [(
        r["symbol"], r["security_name"], r["exchange"], r["cqs_symbol"],
        r["market_category"], r["test_issue"], r["financial_status"],
        r["round_lot_size"], r["etf"], r["secondary_symbol"]
    ) for r in records]
    with conn.cursor() as cur:
        execute_values(cur, sql, vals)
    conn.commit()

def update_last_updated(conn):
    logger.info("Updating last_updated timestamp")
    with conn.cursor() as cur:
        cur.execute("""
          INSERT INTO last_updated (script_name, last_run)
          VALUES (%s, NOW())
          ON CONFLICT (script_name) DO UPDATE
            SET last_run = EXCLUDED.last_run;
        """, ('loadstocksymbols.py',))
    conn.commit()

# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    logger.info("Starting download of symbol lists")
    nas_text = requests.get(NASDAQ_LISTED_URL).text
    oth_text = requests.get(OTHER_LISTED_URL).text
    logger.info("Downloaded NASDAQ (%d bytes), Other (%d bytes)",
                len(nas_text), len(oth_text))

    # parse
    nas = choose_parser(nas_text)(nas_text)
    oth = choose_parser(oth_text)(oth_text)
    logger.info("Parsed %d NASDAQ, %d Other", len(nas), len(oth))

    # dedupe & filter
    combined = nas + oth
    deduped = {r["symbol"]: r for r in combined}.values()
    final = [r for r in deduped if "$" not in r["symbol"]]
    logger.info("%d unique, %d filtered by '$'",
                len(final), len(deduped) - len(final))

    # write to Postgres
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )
    try:
        init_db_schema(conn)
        insert_records(conn, final)
        update_last_updated(conn)
        logger.info("Done: %d symbols loaded", len(final))
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error in loadstocksymbols")
        sys.exit(1)
