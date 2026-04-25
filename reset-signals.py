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

# Drop existing signal tables
for table in ['buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly']:
    cursor.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
    conn.commit()

# Create correct schema
sql = """
CREATE TABLE buy_sell_daily (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

CREATE TABLE buy_sell_weekly (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);

CREATE TABLE buy_sell_monthly (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20)    NOT NULL,
    timeframe    VARCHAR(10)    NOT NULL,
    date         DATE           NOT NULL,
    open         REAL,
    high         REAL,
    low          REAL,
    close        REAL,
    volume       BIGINT,
    signal       VARCHAR(10),
    buylevel     REAL,
    stoplevel    REAL,
    inposition   BOOLEAN,
    UNIQUE(symbol, timeframe, date)
);
"""

try:
    cursor.execute(sql)
    conn.commit()
    print("OK - Signal tables recreated")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

cursor.close()
conn.close()
