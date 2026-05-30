#!/usr/bin/env python3
import csv
import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import boto3
except ImportError:
    boto3 = None

from utils.database_context import DatabaseContext
import psycopg2
from psycopg2.extras import execute_values
import requests

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("loadstocksymbols")

# ─── Data Source URLs ──────────────────────────────────────────────────────────
NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")

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
    # SPAC and blank check company filters
    r"\bblank check\b",
    r"\bspac\b",
    r"\bspecial purpose\b",
    r"\binvestment corp\b",
    # Low-quality/shell company filters (keep legit foreign companies like BABA)
    r"\bAardvark\b",  # Aardvark Therapeutics - micro-cap shell
]

def should_exclude(name: str) -> bool:
    return any(re.search(p, name, flags=re.IGNORECASE) for p in PATTERNS)

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
        # Skip class shares (.A, .B, .C) — often missing from yfinance
        if re.match(r'^[A-Z]+\.[A-Z]$', sym):
            continue
        # Skip test issues and deficient financial status
        if r.get("Test Issue", "").upper() == "Y":
            continue
        if r.get("Financial Status", "").strip() == "D":
            continue
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append(
            {
                "symbol": sym,
                "security_name": name,
                "exchange": "NASDAQ",
                "cqs_symbol": None,
                "market_category": r.get("Market Category", "").strip(),
                "test_issue": r.get("Test Issue", "").strip(),
                "financial_status": r.get("Financial Status", "").strip(),
                "round_lot_size": lot,
                "etf": r.get("ETF", "").strip(),
                "secondary_symbol": r.get("NextShares", "").strip(),
            }
        )
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
        rows.append(
            {
                "symbol": sym,
                "security_name": name,
                "exchange": "NASDAQ",
                "cqs_symbol": None,
                "market_category": r.get("Market Category", "").strip(),
                "test_issue": r.get("Test Issue", "").strip(),
                "financial_status": r.get("Financial Status", "").strip(),
                "round_lot_size": lot,
                "etf": r.get("ETF", "").strip(),
                "secondary_symbol": r.get("NextShares", "").strip(),
            }
        )
    return rows

def parse_other(text: str):
    rows = []
    exch_map = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets",
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
        # Skip class shares (.A, .B, .C) — often missing from yfinance
        if re.match(r'^[A-Z]+\.[A-Z]$', sym):
            continue
        # Skip test issues and deficient financial status
        if r.get("Test Issue", "").upper() == "Y":
            continue
        if r.get("Financial Status", "").strip() == "D":
            continue
        try:
            lot = int(r.get("Round Lot Size") or 0)
        except ValueError:
            lot = None
        rows.append(
            {
                "symbol": sym,
                "security_name": name,
                "exchange": exch_map.get(r.get("Exchange"), r.get("Exchange", "")),
                "cqs_symbol": r.get("CQS Symbol", "").strip(),
                "market_category": None,
                "test_issue": r.get("Test Issue", "").strip(),
                "financial_status": None,
                "round_lot_size": lot,
                "etf": r.get("ETF", "").strip(),
                "secondary_symbol": r.get("NASDAQ Symbol", "").strip(),
            }
        )
    return rows

def parse_other_etf(text: str):
    rows = []
    exch_map = {
        "A": "American Stock Exchange",
        "N": "New York Stock Exchange",
        "P": "NYSE Arca",
        "Z": "BATS Global Markets",
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
        rows.append(
            {
                "symbol": sym,
                "security_name": name,
                "exchange": exch_map.get(r.get("Exchange"), r.get("Exchange", "")),
                "cqs_symbol": r.get("CQS Symbol", "").strip(),
                "market_category": None,
                "test_issue": r.get("Test Issue", "").strip(),
                "financial_status": None,
                "round_lot_size": lot,
                "etf": r.get("ETF", "").strip(),
                "secondary_symbol": r.get("NASDAQ Symbol", "").strip(),
            }
        )
    return rows

# ─── DB Utilities ─────────────────────────────────────────────────────────────
def init_db(cur):
    logger.info("Ensuring tables exist (never drop - avoid data loss)")
    # stock_symbols
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_symbols (
            symbol            VARCHAR(50) PRIMARY KEY,
            exchange          VARCHAR(100),
            security_name     TEXT,
            cqs_symbol        VARCHAR(50),
            market_category   VARCHAR(50),
            test_issue        CHAR(1),
            financial_status  VARCHAR(50),
            round_lot_size    INT,
            etf               CHAR(1),
            secondary_symbol  VARCHAR(50),
            is_sp500          BOOLEAN DEFAULT FALSE
        );
    """
    )
    # Add is_sp500 column if it doesn't exist (for existing tables)
    cur.execute(
        """
        ALTER TABLE stock_symbols
        ADD COLUMN IF NOT EXISTS is_sp500 BOOLEAN DEFAULT FALSE;
    """
    )
    # etf_symbols
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_symbols (
            symbol            VARCHAR(50) PRIMARY KEY,
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
    """
    )
    # last_updated
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS last_updated (
            script_name   VARCHAR(255) PRIMARY KEY,
            last_run      TIMESTAMP WITH TIME ZONE
        );
    """
    )

def insert_all(cur, records):
    logger.info("Inserting %d stock records", len(records))
    sql = """
      INSERT INTO stock_symbols (
        symbol, security_name, exchange
      ) VALUES %s
      ON CONFLICT (symbol) DO UPDATE SET
        security_name = EXCLUDED.security_name,
        exchange = EXCLUDED.exchange;
    """
    values = [
        (
            r["symbol"],
            r["security_name"],
            r["exchange"],
        )
        for r in records
    ]
    execute_values(cur, sql, values)

def insert_etfs(cur, records):
    logger.info("Inserting %d ETF records", len(records))
    sql = """
      INSERT INTO stock_symbols (
        symbol, security_name, exchange
      ) VALUES %s
      ON CONFLICT (symbol) DO UPDATE SET
        security_name = EXCLUDED.security_name,
        exchange = EXCLUDED.exchange;
    """
    values = [
        (
            r["symbol"],
            r["security_name"],
            r["exchange"],
        )
        for r in records
    ]
    execute_values(cur, sql, values)

def update_timestamp(cur):
    logger.info("Updating last_updated timestamp")
    cur.execute(
        """
        INSERT INTO last_updated (script_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (script_name) DO UPDATE
          SET last_run = EXCLUDED.last_run;
    """,
        ("loadstocksymbols.py",),
    )

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("Downloading NASDAQ list")
    nas_text = requests.get(NASDAQ_URL, timeout=15).text
    logger.info("Downloading OTHER list")
    oth_text = requests.get(OTHER_URL, timeout=15).text

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

    with DatabaseContext('write') as conn:
        init_db(conn)
        insert_all(conn, all_records)
        insert_etfs(conn, all_etf_records)
        update_timestamp(conn)
        logger.info("Load complete")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
