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
    # (re-use the full list you have)
    r"\bpreferred\b", r"\bwarrant(s)?\b", r"\betf\b", r"\btrust\b"
]

# Store filtered-out entries for CSV
excluded_records = []

def should_filter(security_name):
    return any(re.search(p, security_name, flags=re.IGNORECASE) for p in patterns)

def download_text_file(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

def parse_nasdaq_listed(text):
    records = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row["Symbol"].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        if row["ETF"].strip().upper() == "Y" or should_filter(name):
            excluded_records.append({
                "source": "NASDAQ",
                "symbol": row["Symbol"].strip(),
                "security_name": name
            })
            continue
        try:
            lot = int(row["Round Lot Size"])
        except:
            lot = None
        records.append({
            "symbol":            row["Symbol"].strip(),
            "security_name":     name,
            "exchange":          "NASDAQ",
            "cqs_symbol":        None,
            "market_category":   row["Market Category"].strip(),
            "test_issue":        row["Test Issue"].strip(),
            "financial_status":  row["Financial Status"].strip(),
            "round_lot_size":    lot,
            "etf":               row["ETF"].strip(),
            "secondary_symbol":  row["NextShares"].strip()
        })
    return records

def parse_other_listed(text):
    records = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    exch_map = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets"
    }
    for row in reader:
        if row["ACT Symbol"].startswith("File Creation Time"):
            continue
        name = row["Security Name"].strip()
        if row["ETF"].strip().upper() == "Y" or should_filter(name):
            excluded_records.append({
                "source": "Other",
                "symbol": row["ACT Symbol"].strip(),
                "security_name": name
            })
            continue
        try:
            lot = int(row["Round Lot Size"])
        except:
            lot = None
        exch = exch_map.get(row["Exchange"].strip(), row["Exchange"].strip())
        records.append({
            "symbol":            row["ACT Symbol"].strip(),
            "security_name":     name,
            "exchange":          exch,
            "cqs_symbol":        row["CQS Symbol"].strip(),
            "market_category":   None,
            "test_issue":        row["Test Issue"].strip(),
            "financial_status":  None,
            "round_lot_size":    lot,
            "etf":               row["ETF"].strip(),
            "secondary_symbol":  row["NASDAQ Symbol"].strip()
        })
    return records

def deduplicate_records(records):
    seen = {}
    for r in records:
        if r["symbol"] not in seen:
            seen[r["symbol"]] = r
    return list(seen.values())

def write_excluded_csv(filename="excluded_records.csv"):
    if not excluded_records:
        print("ℹ️  No excluded records to write.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["source","symbol","security_name"])
        w.writeheader()
        w.writerows(excluded_records)
    print(f"📄 Excluded records saved to {filename}")

def write_included_csv(records, filename="included_records.csv"):
    if not records:
        print("ℹ️  No included records to write.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        fields = ["symbol","security_name","exchange","cqs_symbol",
                  "market_category","test_issue","financial_status",
                  "round_lot_size","etf","secondary_symbol"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)
    print(f"📄 Included records saved to {filename}")

def insert_into_postgres(records):
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
      cqs_symbol VARCHAR(50),
      market_category VARCHAR(50),
      test_issue CHAR(1),
      financial_status VARCHAR(50),
      round_lot_size INT,
      etf CHAR(1),
      secondary_symbol VARCHAR(50)
    );
    """
    upsert_sql = """
    INSERT INTO stock_symbols
      (symbol,security_name,exchange,cqs_symbol,market_category,
       test_issue,financial_status,round_lot_size,etf,secondary_symbol)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS stock_symbols;")
                cur.execute(create_sql)
                for r in records:
                    cur.execute(upsert_sql, (
                        r["symbol"], r["security_name"], r["exchange"],
                        r["cqs_symbol"], r["market_category"], r["test_issue"],
                        r["financial_status"], r["round_lot_size"],
                        r["etf"], r["secondary_symbol"]
                    ))
    finally:
        conn.close()

def main():
    print("📥 Downloading NASDAQ...")
    nas = parse_nasdaq_listed(download_text_file(NASDAQ_LISTED_URL))
    print("📥 Downloading Other...")
    oth = parse_other_listed(download_text_file(OTHER_LISTED_URL))
    all_rec = nas + oth
    print(f"✅ Before dedupe: {len(all_rec)} records")
    unique = deduplicate_records(all_rec)
    print(f"✅ After dedupe: {len(unique)} records")
    final = [r for r in unique if "$" not in r["symbol"]]
    print(f"✅ After $-filter: {len(final)} records")
    insert_into_postgres(final)
    write_excluded_csv()
    write_included_csv(final)
    print("🚀 Done!")

if __name__ == "__main__":
    main()
    # Update last_updated table
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS last_updated (
                  script_name TEXT PRIMARY KEY,
                  last_updated TIMESTAMP
                );
                """)
                cur.execute("""
                INSERT INTO last_updated (script_name, last_updated)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                  SET last_updated = EXCLUDED.last_updated;
                """, ('loadstocksymbols.py',))
        print("✅ last_updated table updated.")
    finally:
        conn.close()
