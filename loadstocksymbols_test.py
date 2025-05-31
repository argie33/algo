#!/usr/bin/env python3
import os
import sys
import json
import logging
import boto3
import psycopg2
from psycopg2.extras import execute_values

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger("loadstocksymbols_test")

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

# ─── Test Data ────────────────────────────────────────────────────────────────
TEST_STOCKS = [
    {
        "symbol": "AAPL",
        "security_name": "Apple Inc.",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "N",
        "secondary_symbol": None
    },
    {
        "symbol": "MSFT",
        "security_name": "Microsoft Corporation",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "N",
        "secondary_symbol": None
    },
    {
        "symbol": "GOOGL",
        "security_name": "Alphabet Inc.",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "N",
        "secondary_symbol": None
    },
    {
        "symbol": "AMZN",
        "security_name": "Amazon.com Inc.",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "N",
        "secondary_symbol": None
    },
    {
        "symbol": "META",
        "security_name": "Meta Platforms Inc.",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "N",
        "secondary_symbol": None
    }
]

TEST_ETFS = [
    {
        "symbol": "SPY",
        "security_name": "SPDR S&P 500 ETF Trust",
        "exchange": "NYSE Arca",
        "cqs_symbol": "SPY",
        "market_category": None,
        "test_issue": "N",
        "financial_status": None,
        "round_lot_size": 100,
        "etf": "Y",
        "secondary_symbol": None
    },
    {
        "symbol": "QQQ",
        "security_name": "Invesco QQQ Trust",
        "exchange": "NASDAQ",
        "cqs_symbol": None,
        "market_category": "Q",
        "test_issue": "N",
        "financial_status": "N",
        "round_lot_size": 100,
        "etf": "Y",
        "secondary_symbol": None
    },
    {
        "symbol": "IWM",
        "security_name": "iShares Russell 2000 ETF",
        "exchange": "NYSE Arca",
        "cqs_symbol": "IWM",
        "market_category": None,
        "test_issue": "N",
        "financial_status": None,
        "round_lot_size": 100,
        "etf": "Y",
        "secondary_symbol": None
    },
    {
        "symbol": "VTI",
        "security_name": "Vanguard Total Stock Market ETF",
        "exchange": "NYSE Arca",
        "cqs_symbol": "VTI",
        "market_category": None,
        "test_issue": "N",
        "financial_status": None,
        "round_lot_size": 100,
        "etf": "Y",
        "secondary_symbol": None
    },
    {
        "symbol": "VOO",
        "security_name": "Vanguard S&P 500 ETF",
        "exchange": "NYSE Arca",
        "cqs_symbol": "VOO",
        "market_category": None,
        "test_issue": "N",
        "financial_status": None,
        "round_lot_size": 100,
        "etf": "Y",
        "secondary_symbol": None
    }
]

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
        """, ("loadstocksymbols_test.py",))
    conn.commit()

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    logger.info("Using test data with 5 stocks and 5 ETFs")
    
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB
    )
    try:
        init_db(conn)
        insert_all(conn, TEST_STOCKS)
        insert_etfs(conn, TEST_ETFS)
        update_timestamp(conn)
        logger.info("Test data load complete")
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)