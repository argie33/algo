#!/usr/bin/env python3
import os, psycopg2

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', 5432)),
    database=os.getenv('DB_NAME', 'stocks'),
    user=os.getenv('DB_USER', 'stocks'),
    password=os.getenv('DB_PASSWORD', 'stocks')
)
cur = conn.cursor()

# Check TTM table schemas
tables = ['ttm_income_statement', 'ttm_cash_flow', 'quarterly_income_statement', 'quarterly_cash_flow']

for table in tables:
    print(f"\n{table} schema:")
    cur.execute(f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = '{table}'
        ORDER BY ordinal_position
    """)
    for col in cur.fetchall():
        print(f"  {col[0]:30} {col[1]}")

cur.close()
conn.close()
