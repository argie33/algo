import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

# Create missing annual_balance_sheet (copy quarterly structure)
sql = """
DROP TABLE IF EXISTS annual_balance_sheet CASCADE;
CREATE TABLE annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    date DATE,
    total_assets BIGINT,
    total_liabilities BIGINT,
    stockholders_equity BIGINT,
    total_debt BIGINT,
    cash BIGINT,
    current_assets BIGINT,
    current_liabilities BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);

DROP TABLE IF EXISTS sector_ranking CASCADE;
CREATE TABLE sector_ranking (
    id SERIAL PRIMARY KEY,
    sector_name VARCHAR(100),
    sector VARCHAR(100),
    rank INT,
    price_change FLOAT,
    volume BIGINT,
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS sector_performance CASCADE;
CREATE TABLE sector_performance (
    id SERIAL PRIMARY KEY,
    sector VARCHAR(100),
    performance FLOAT,
    date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol, date DESC);
CREATE INDEX IF NOT EXISTS idx_sector_ranking_sector ON sector_ranking(sector_name);
CREATE INDEX IF NOT EXISTS idx_sector_performance_sector ON sector_performance(sector);
"""

try:
    cursor.execute(sql)
    conn.commit()
    print("✅ Created missing tables")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

conn.close()
