



#!/usr/bin/env python3
import re
import csv
import requests
import json
import boto3
import psycopg2
from psycopg2.extras import DictCursor
from os import getenv

# -------------------------------
# Script metadata
# -------------------------------
SCRIPT_NAME = "loadstocksymbols.py"

# -------------------------------
# Environment-driven configuration
# -------------------------------
PG_HOST       = getenv("DB_ENDPOINT")
PG_PORT       = int(getenv("DB_PORT", "5432"))
PG_DB         = getenv("DB_NAME")
DB_SECRET_ARN = getenv("DB_SECRET_ARN")

# -------------------------------
# Data URLs & regex for classification
# -------------------------------
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
patterns   = [
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

def get_db_creds():
    """Fetch username/password from Secrets Manager."""
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=DB_SECRET_ARN)
    sec = json.loads(resp["SecretString"])
    return sec["username"], sec["password"]

def download_text_file(url):
    r = requests.get(url)
    r.raise_for_status()
    return r.text

def parse_listed(text, source):
    rows = []
    key = "Symbol" if source == "NASDAQ" else "ACT Symbol"
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    for row in reader:
        if row[key].startswith("File Creation Time"):
            continue
        name   = row["Security Name"].strip()
        is_etf = row.get("ETF","").upper() == "Y"
        match  = any(re.search(p, name, flags=re.IGNORECASE) for p in patterns)
        if is_etf:
            continue
        try:
            lot = int(row.get("Round Lot Size","0") or 0)
        except:
            lot = None
        rows.append({
            "symbol":         row[key].strip(),
            "security_name":  name,
            "exchange":       source,
            "test_issue":     row.get("Test Issue","").strip(),
            "round_lot_size": lot,
            "security_type":  "other security" if match else "standard"
        })
    return rows

def dedupe(records):
    seen = {}
    for r in records:
        seen.setdefault(r["symbol"], r)
    return list(seen.values())

def insert_into_postgres(records):
    user, pwd = get_db_creds()
    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=user,
        password=pwd,
        dbname=PG_DB,
        sslmode='require',
        cursor_factory=DictCursor
    )
    with conn:
        with conn.cursor() as cur:
            # 1. Ensure tables exist
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS last_updated (
                  script_name      VARCHAR(255) PRIMARY KEY,
                  last_run         TIMESTAMPTZ
                );
            """)

            # 2. Determine existing vs incoming symbols
            cur.execute("SELECT symbol FROM stock_symbols;")
            existing = {row["symbol"] for row in cur.fetchall()}
            incoming = {r["symbol"] for r in records}

            new_symbols     = incoming - existing
            removed_symbols = existing - incoming

            # 3. Upsert all incoming (inserts new + updates metadata if changed)
            upsert = """
                INSERT INTO stock_symbols
                  (symbol, security_name, exchange, test_issue, round_lot_size, security_type)
                VALUES (%s, %s, %s, %s, %s, %s)
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

            # 4. Delete any symbols no longer returned
            if removed_symbols:
                cur.execute(
                    "DELETE FROM stock_symbols WHERE symbol = ANY(%s);",
                    (list(removed_symbols),)
                )

            # 5. Record this run in last_updated
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                  SET last_run = EXCLUDED.last_run;
            """, (SCRIPT_NAME,))

    conn.close()

def handler(event, context):
    print("Starting loadstocksymbols, connecting to", PG_HOST)
    nas = parse_listed(download_text_file(NASDAQ_URL), "NASDAQ")
    oth = parse_listed(download_text_file(OTHER_URL),  "Other")
    all_records = dedupe(nas + oth)
    final = [r for r in all_records if "$" not in r["symbol"]]
    insert_into_postgres(final)
    return {
        "statusCode": 200,
        "body": f"Processed {len(final)} symbols; inventory is now up-to-date."
    }
