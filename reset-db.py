#!/usr/bin/env python3
"""Reset database to match loader schemas exactly"""
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

# Drop ALL tables first with CASCADE
drop_tables = [
    "DROP TABLE IF EXISTS fundamental_metrics CASCADE;",
    "DROP TABLE IF EXISTS market_data CASCADE;",
    "DROP TABLE IF EXISTS price_daily CASCADE;",
    "DROP TABLE IF EXISTS etf_price_daily CASCADE;",
    "DROP TABLE IF EXISTS stock_symbols CASCADE;",
    "DROP TABLE IF EXISTS etf_symbols CASCADE;",
    "DROP TABLE IF EXISTS company_profile CASCADE;",
    "DROP TABLE IF EXISTS annual_balance_sheet CASCADE;",
    "DROP TABLE IF EXISTS key_metrics CASCADE;",
    "DROP TABLE IF EXISTS last_updated CASCADE;",
    "DROP TABLE IF EXISTS buy_sell_daily CASCADE;",
    "DROP TABLE IF EXISTS buy_sell_weekly CASCADE;",
    "DROP TABLE IF EXISTS buy_sell_monthly CASCADE;",
    "DROP TABLE IF EXISTS growth_metrics CASCADE;",
    "DROP TABLE IF EXISTS momentum_metrics CASCADE;",
    "DROP TABLE IF EXISTS stability_metrics CASCADE;",
    "DROP TABLE IF EXISTS value_metrics CASCADE;",
    "DROP TABLE IF EXISTS quality_metrics CASCADE;",
    "DROP TABLE IF EXISTS positioning_metrics CASCADE;",
]

for drop in drop_tables:
    try:
        cursor.execute(drop)
        conn.commit()
    except:
        conn.rollback()

# Read and execute the reset script
with open('webapp/lambda/scripts/reset-database-to-loaders.sql', 'r') as f:
    sql = f.read()

# Remove the DROP statements since we already ran them
sql = '\n'.join([line for line in sql.split('\n') if not line.strip().startswith('DROP')])

# Execute
try:
    cursor.execute(sql)
    conn.commit()
    print("OK - Database reset complete")
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()

cursor.close()
conn.close()
