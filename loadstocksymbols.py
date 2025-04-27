#!/usr/bin/env python3
import re
import csv
import requests
import psycopg2
from psycopg2.extras import DictCursor
from os import getenv

# -------------------------------
# PostgreSQL Connection Configuration
# -------------------------------
PG_HOST     = getenv("DB_ENDPOINT")
PG_PORT     = int(getenv("DB_PORT", "5432"))
PG_USER     = getenv("DB_USER")
PG_PASSWORD = getenv("DB_PASS")
PG_DB       = getenv("DB_NAME")

# -------------------------------
# Data Source URLs
# -------------------------------
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# -------------------------------
# Regex Patterns for Filtering Out Unwanted Securities
# -------------------------------
patterns = [
    # (paste in your full list here)
    r"\bpreferred\b", r"\bredeemable warrant(s)?\b", r"\bwarrant(s)?\b",
    # …
    r"\btrust etf\b", r"\bcapital trust\b"
]

excluded_records = []

def should_filter(name):
    return any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)

def download_text_file(url):
    resp = requests.get(url); resp.raise_for_status(); return resp.text

def parse_listed(text, source):
    records = []
    key = "Symbol" if source=="NASDAQ" else "ACT Symbol"
    exchanger = "NASDAQ" if source=="NASDAQ" else None
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row[key].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        if row.get("ETF","").upper()=="Y" or should_filter(name):
            excluded_records.append({"source":source,"symbol":row[key].strip(),"security_name":name})
            continue
        try: lot = int(row.get("Round Lot Size","0") or 0)
        except: lot = None
        records.append({
            "symbol":           row[key].strip(),
            "security_name":    name,
            "exchange":         source if source=="NASDAQ" else row.get("Exchange","").strip(),
            "cqs_symbol":       row.get("CQS Symbol") if source!="NASDAQ" else None,
            "market_category":  row.get("Market Category") if source=="NASDAQ" else None,
            "test_issue":       row.get("Test Issue","").strip(),
            "financial_status": row.get("Financial Status") if source=="NASDAQ" else None,
            "round_lot_size":   lot,
            "etf":              row.get("ETF","").strip(),
            "secondary_symbol": row.get("NextShares") if source=="NASDAQ" else row.get("NASDAQ Symbol")
        })
    return records

def dedupe(records):
    seen = {}
    for r in records:
        if r["symbol"] not in seen:
            seen[r["symbol"]] = r
    return list(seen.values())

def insert_into_postgres(recs):
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB, cursor_factory=DictCursor
    )
    create_sql = """
      CREATE TABLE IF NOT EXISTS stock_symbols (
        symbol VARCHAR(50) PRIMARY KEY,
        security_name TEXT,
        exchange VARCHAR(100),
        test_issue CHAR(1),
        round_lot_size INT
      );
    """
    upsert_sql = """
      INSERT INTO stock_symbols(symbol,security_name,exchange,test_issue,round_lot_size)
      VALUES(%s,%s,%s,%s,%s)
      ON CONFLICT(symbol) DO UPDATE
        SET security_name = EXCLUDED.security_name,
            exchange      = EXCLUDED.exchange,
            test_issue    = EXCLUDED.test_issue,
            round_lot_size= EXCLUDED.round_lot_size;
    """
    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stock_symbols;")
            cur.execute(create_sql)
            for r in recs:
                cur.execute(upsert_sql, (
                    r["symbol"], r["security_name"], r["exchange"],
                    r["test_issue"], r["round_lot_size"]
                ))
    conn.close()

def handler(event, context):
    nas = parse_listed(download_text_file(NASDAQ_LISTED_URL), "NASDAQ")
    oth = parse_listed(download_text_file(OTHER_LISTED_URL), "Other")
    allrec = dedupe(nas + oth)
    final = [r for r in allrec if "$" not in r["symbol"]]
    insert_into_postgres(final)
    return {"statusCode":200, "body": f"Loaded {len(final)} symbols"}
