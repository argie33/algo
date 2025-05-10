#!/usr/bin/env python3
import os
import re
import csv
import json
import requests
import boto3
import psycopg2
from psycopg2.extras import execute_values

# -------------------------------
# Postgres Connection Configuration
#   now via Secrets Manager
# -------------------------------
DB_SECRET_ARN = os.environ["DB_SECRET_ARN"]

def get_db_config():
    """Fetch host, port, user, password, dbname from Secrets Manager."""
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

# -------------------------------
# Data Source URLs
# -------------------------------
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# -------------------------------
# Regex Patterns for Filtering Out Unwanted Securities
# -------------------------------
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

def should_filter(security_name):
    """Return True if the security name matches any unwanted pattern."""
    for pattern in patterns:
        if re.search(pattern, security_name, flags=re.IGNORECASE):
            return True
    return False

# Collect filtered-out records if you ever need them
excluded_records = []

def download_text_file(url):
    """Download and return the text contents of a file from a URL."""
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

def parse_nasdaq_listed(text):
    """Parse NASDAQ-listed file into unified record dicts."""
    records = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row["Symbol"].strip().startswith("File Creation Time"):
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
            lot = int(row["Round Lot Size"].strip())
        except:
            lot = None

        records.append({
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
    return records

def parse_other_listed(text):
    """Parse Other-listed file into unified record dicts."""
    exchange_mapping = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets"
    }
    records = []
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row["ACT Symbol"].strip().startswith("File Creation Time"):
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
            lot = int(row["Round Lot Size"].strip())
        except:
            lot = None

        code = row["Exchange"].strip()
        full_exch = exchange_mapping.get(code, code)

        records.append({
            "symbol": row["ACT Symbol"].strip(),
            "security_name": name,
            "exchange": full_exch,
            "cqs_symbol": row["CQS Symbol"].strip(),
            "market_category": None,
            "test_issue": row["Test Issue"].strip(),
            "financial_status": None,
            "round_lot_size": lot,
            "etf": row["ETF"].strip(),
            "secondary_symbol": row["NASDAQ Symbol"].strip()
        })
    return records

def deduplicate_records(records):
    """Deduplicate by 'symbol', keeping the first occurrence."""
    unique = {}
    for r in records:
        if r["symbol"] not in unique:
            unique[r["symbol"]] = r
    return list(unique.values())

def init_db_schema(conn):
    """Drop & recreate the stock_symbols table exactly once."""
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
    conn.commit()

def insert_records(conn, records):
    """Bulk insert all records in one shot, with upsert on symbol."""
    sql = """
    INSERT INTO stock_symbols (
        symbol, security_name, exchange, cqs_symbol,
        market_category, test_issue, financial_status,
        round_lot_size, etf, secondary_symbol
    ) VALUES %s
    ON CONFLICT (symbol) DO UPDATE SET
        security_name     = EXCLUDED.security_name,
        exchange          = EXCLUDED.exchange,
        cqs_symbol        = EXCLUDED.cqs_symbol,
        market_category   = EXCLUDED.market_category,
        test_issue        = EXCLUDED.test_issue,
        financial_status  = EXCLUDED.financial_status,
        round_lot_size    = EXCLUDED.round_lot_size,
        etf               = EXCLUDED.etf,
        secondary_symbol  = EXCLUDED.secondary_symbol;
    """
    values = [
        (
            r["symbol"], r["security_name"], r["exchange"], r["cqs_symbol"],
            r["market_category"], r["test_issue"], r["financial_status"],
            r["round_lot_size"], r["etf"], r["secondary_symbol"]
        ) for r in records
    ]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()

def update_last_updated(conn):
    """Record this script’s last run timestamp."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO last_updated (script_name, last_updated)
            VALUES (%s, NOW())
            ON CONFLICT (script_name) DO UPDATE
              SET last_updated = EXCLUDED.last_updated;
        """, ('loadstocksymbols.py',))
    conn.commit()

def main():
    # 1) Download both files
    nas_text = download_text_file(NASDAQ_LISTED_URL)
    oth_text = download_text_file(OTHER_LISTED_URL)

    # 2) Parse each into record lists
    nas = parse_nasdaq_listed(nas_text)
    oth = parse_other_listed(oth_text)

    # 3) Combine and dedupe
    all_records = deduplicate_records(nas + oth)

    # 4) Filter out "$" symbols
    filtered = []
    for r in all_records:
        if "$" in r["symbol"]:
            excluded_records.append({
                "source": "DollarFilter",
                "symbol": r["symbol"],
                "security_name": r["security_name"]
            })
        else:
            filtered.append(r)

    # 5) Connect, init schema once, bulk insert, update timestamp
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )
    try:
        init_db_schema(conn)
        insert_records(conn, filtered)
        update_last_updated(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
