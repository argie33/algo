#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).parent / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

sql = """
DROP TABLE IF EXISTS stock_symbols CASCADE;
DROP TABLE IF EXISTS etf_symbols CASCADE;

CREATE TABLE stock_symbols (
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
    is_sp500          BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE etf_symbols (
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
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

try:
    cursor.execute(sql)
    conn.commit()
    print("OK - Symbol tables created")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

cursor.close()
conn.close()
