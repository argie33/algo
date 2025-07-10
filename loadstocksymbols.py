#!/usr/bin/env python3
# Fixed duplicate symbols in matrix - should run only once now
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
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols")

# ─── Config ────────────────────────────────────────────────────────────────────
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
if not DB_SECRET_ARN:
    logger.error("DB_SECRET_ARN not set; aborting")
    sys.exit(1)

def get_db_cfg():
    client = boto3.client("secretsmanager")
    secret = json.loads(client.get_secret_value(SecretId=DB_SECRET_ARN)["SecretString"])
    return (
        secret["host"],
        secret.get("port", "5432"),
        secret["username"],
        secret["password"],
        secret["dbname"]
    )

PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB = get_db_cfg()

# ─── Data Source URLs ──────────────────────────────────────────────────────────
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# ─── Exclusion patterns ────────────────────────────────────────────────────────
PATTERNS = [
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
    r"\bspecial purpose\b",  
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

def should_exclude(name: str) -> bool:
    return any(re.search(p, name, flags=re.IGNORECASE) for p in PATTERNS)

# ─── Parsers ──────────────────────────────────────────────────────────────────
def parse_nasdaq(text: str):
    rows = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for r in reader:
        sym = r.get("Symbol", "").strip()
        if not sym or sym.startswith("File Creation Time"):
            continue
        name = r.get("Security Name", "").strip()
        # skip ETFs here
        if r.get("ETF", "").upper() == "Y" or should_exclude(name):
            continue
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append({
            "symbol":           sym,
            "security_name":    name,
            "exchange":         "NASDAQ",
            "cqs_symbol":       None,
            "market_category":  r.get("Market Category", "").strip(),
            "test_issue":       r.get("Test Issue", "").strip(),
            "financial_status": r.get("Financial Status", "").strip(),
            "round_lot_size":   lot,
            "etf":              r.get("ETF", "").strip(),
            "secondary_symbol": r.get("NextShares", "").strip(),
        })
    return rows

def parse_nasdaq_etf(text: str):
    rows = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for r in reader:
        sym = r.get("Symbol", "").strip()
        if not sym or sym.startswith("File Creation Time"):
            continue
        # only ETFs
        if r.get("ETF", "").upper() != "Y":
            continue
        name = r.get("Security Name", "").strip()
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append({
            "symbol":           sym,
            "security_name":    name,
            "exchange":         "NASDAQ",
            "cqs_symbol":       None,
            "market_category":  r.get("Market Category", "").strip(),
            "test_issue":       r.get("Test Issue", "").strip(),
            "financial_status": r.get("Financial Status", "").strip(),
            "round_lot_size":   lot,
            "etf":              r.get("ETF", "").strip(),
            "secondary_symbol": r.get("NextShares", "").strip(),
        })
    return rows

def parse_other(text: str):
    rows = []
    exch_map = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets"
    }
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for r in reader:
        sym = r.get("ACT Symbol", "").strip()
        if not sym or sym.startswith("File Creation Time"):
            continue
        name = r.get("Security Name", "").strip()
        # skip ETFs here
        if r.get("ETF", "").upper() == "Y" or should_exclude(name):
            continue
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append({
            "symbol":           sym,
            "security_name":    name,
            "exchange":         exch_map.get(r.get("Exchange"), r.get("Exchange", "")),
            "cqs_symbol":       r.get("CQS Symbol", "").strip(),
            "market_category":  None,
            "test_issue":       r.get("Test Issue", "").strip(),
            "financial_status": None,
            "round_lot_size":   lot,
            "etf":              r.get("ETF", "").strip(),
            "secondary_symbol": r.get("NASDAQ Symbol", "").strip(),
        })
    return rows

def parse_other_etf(text: str):
    rows = []
    exch_map = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets"
    }
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for r in reader:
        sym = r.get("ACT Symbol", "").strip()
        if not sym or sym.startswith("File Creation Time"):
            continue
        # only ETFs
        if r.get("ETF", "").upper() != "Y":
            continue
        name = r.get("Security Name", "").strip()
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append({
            "symbol":           sym,
            "security_name":    name,
            "exchange":         exch_map.get(r.get("Exchange"), r.get("Exchange", "")),
            "cqs_symbol":       r.get("CQS Symbol", "").strip(),
            "market_category":  None,
            "test_issue":       r.get("Test Issue", "").strip(),
            "financial_status": None,
            "round_lot_size":   lot,
            "etf":              r.get("ETF", "").strip(),
            "secondary_symbol": r.get("NASDAQ Symbol", "").strip(),
        })
    return rows

# ─── DB Utilities ─────────────────────────────────────────────────────────────
def init_db(conn):
    logger.info("Dropping and recreating tables")
    with conn.cursor() as cur:
        # stock_symbols
        cur.execute("DROP TABLE IF EXISTS stock_symbols;")
        cur.execute("""
            CREATE TABLE stock_symbols (
                symbol            VARCHAR(50),
                exchange          VARCHAR(100),
                security_name     TEXT,
                cqs_symbol        VARCHAR(50),
                market_category   VARCHAR(50),
                test_issue        CHAR(1),
                financial_status  VARCHAR(50),
                round_lot_size    INT,
                etf               CHAR(1),
                secondary_symbol  VARCHAR(50)
            );
        """)
        # etf_symbols
        cur.execute("DROP TABLE IF EXISTS etf_symbols;")
        cur.execute("""
            CREATE TABLE etf_symbols (
                symbol            VARCHAR(50),
                exchange          VARCHAR(100),
                security_name     TEXT,
                cqs_symbol        VARCHAR(50),
                market_category   VARCHAR(50),
                test_issue        CHAR(1),
                financial_status  VARCHAR(50),
                round_lot_size    INT,
                etf               CHAR(1),
                secondary_symbol  VARCHAR(50)
            );
        """)
        # last_updated
        cur.execute("DROP TABLE IF EXISTS last_updated;")
        cur.execute("""
            CREATE TABLE last_updated (
                script_name   VARCHAR(255) PRIMARY KEY,
                last_run      TIMESTAMP WITH TIME ZONE
            );
        """)
    conn.commit()

def insert_all(conn, records):
    logger.info("Inserting %d stock records", len(records))
    sql = """
      INSERT INTO stock_symbols (
        symbol, exchange, security_name, cqs_symbol,
        market_category, test_issue, financial_status,
        round_lot_size, etf, secondary_symbol
      ) VALUES %s;
    """
    values = [(
        r["symbol"], r["exchange"], r["security_name"], r["cqs_symbol"],
        r["market_category"], r["test_issue"], r["financial_status"],
        r["round_lot_size"], r["etf"], r["secondary_symbol"]
    ) for r in records]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()

def insert_etfs(conn, records):
    logger.info("Inserting %d ETF records", len(records))
    sql = """
      INSERT INTO etf_symbols (
        symbol, exchange, security_name, cqs_symbol,
        market_category, test_issue, financial_status,
        round_lot_size, etf, secondary_symbol
      ) VALUES %s;
    """
    values = [(
        r["symbol"], r["exchange"], r["security_name"], r["cqs_symbol"],
        r["market_category"], r["test_issue"], r["financial_status"],
        r["round_lot_size"], r["etf"], r["secondary_symbol"]
    ) for r in records]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()

def update_timestamp(conn):
    logger.info("Updating last_updated timestamp")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_run)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_run = EXCLUDED.last_run;
        """, ("loadstocksymbols.py",))
    conn.commit()

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("Downloading NASDAQ list")
    nas_text = requests.get(NASDAQ_URL).text
    logger.info("Downloading OTHER list")
    oth_text = requests.get(OTHER_URL).text

    # parse non-ETF stocks
    nas = parse_nasdaq(nas_text)
    oth = parse_other(oth_text)
    all_records = nas + oth

    # parse ETF symbols
    nas_etf = parse_nasdaq_etf(nas_text)
    oth_etf = parse_other_etf(oth_text)
    all_etf_records = nas_etf + oth_etf

    logger.info("Total stock records after filtering: %d", len(all_records))
    logger.info("Total ETF records: %d", len(all_etf_records))
    logger.info("Stock symbols loading process initiated successfully")

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )
    try:
        init_db(conn)
        insert_all(conn, all_records)
        insert_etfs(conn, all_etf_records)
        update_timestamp(conn)
        logger.info("Load complete - symbols updated successfully")
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)
