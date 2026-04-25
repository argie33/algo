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

# Create annual_balance_sheet with CORRECT schema (matches quarterly)
sql = """
DROP TABLE IF EXISTS annual_balance_sheet CASCADE;
CREATE TABLE annual_balance_sheet (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    fiscal_year INT,
    total_assets BIGINT,
    total_liabilities BIGINT,
    stockholders_equity BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_annual_balance_sheet_symbol ON annual_balance_sheet(symbol, fiscal_year DESC);
"""

try:
    cursor.execute(sql)
    conn.commit()
    print("Created annual_balance_sheet")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

conn.close()
