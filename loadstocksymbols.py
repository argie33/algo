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
# Regex Patterns for Classifying Securities
# -------------------------------
patterns = [
    r"\bpreferred\b", r"\bredeemable warrant(s)?\b", r"\bwarrant(s)?\b",
    r"\betf\b", r"\btrust\b",
    # … include your full list here …
]

def download_text_file(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

def parse_listed(text, source):
    rows = []
    key = "Symbol" if source == "NASDAQ" else "ACT Symbol"
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row[key].startswith("File Creation Time"):
            continue

        name = row["Security Name"].strip()
        is_etf = row.get("ETF", "").upper() == "Y"
        match = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)

        # Skip actual ETFs
        if is_etf:
            continue

        security_type = "other security" if match else "standard"

        try:
            lot = int(row.get("Round Lot Size", "0") or 0)
        except:
            lot = None

        rows.append({
            "symbol":         row[key].strip(),
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue", "").strip(),
            "round_lot_size": lot,
            "security_type":  security_type
        })
    return rows

def dedupe(records):
    seen = {}
    for r in records:
        seen.setdefault(r["symbol"], r)
    return list(seen.values())

def insert_into_postgres(records):
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        password=PG_PASSWORD,
        dbname=PG_DB,
        sslmode='require',
        cursor_factory=DictCursor
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock_symbols (
                  symbol           VARCHAR(50) PRIMARY KEY,
                  security_name    TEXT,
                  exchange         VARCHAR(20),
                  test_issue       CHAR(1),
                  round_lot_size   INT,
                  security_type    VARCHAR(20)
                );
            """)
            cur.execute("TRUNCATE TABLE stock_symbols;")
            upsert = """
                INSERT INTO stock_symbols
                  (symbol,security_name,exchange,test_issue,round_lot_size,security_type)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(symbol) DO UPDATE SET
                  security_name  = EXCLUDED.security_name,
                  exchange       = EXCLUDED.exchange,
                  test_issue     = EXCLUDED.test_issue,
                  round_lot_size = EXCLUDED.round_lot_size,
                  security_type  = EXCLUDED.security_type;
            """
            for r in records:
                cur.execute(upsert, (
                    r["symbol"],
                    r["security_name"],
                    r["exchange"],
                    r["test_issue"],
                    r["round_lot_size"],
                    r["security_type"]
                ))
    conn.close()

def handler(event, context):
    print("Invocation start – connecting to", PG_HOST)
    nas = parse_listed(download_text_file(NASDAQ_LISTED_URL), "NASDAQ")
    oth = parse_listed(download_text_file(OTHER_LISTED_URL),  "Other")
    all_records = dedupe(nas + oth)
    final = [r for r in all_records if "$" not in r["symbol"]]
    insert_into_postgres(final)
    return {
        "statusCode": 200,
        "body": f"Loaded {len(final)} symbols with classification"
    }
