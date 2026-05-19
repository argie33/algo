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

# Check empty critical tables
tables_to_check = [
    'quarterly_income_statement',
    'quarterly_balance_sheet',
    'quarterly_cash_flow',
    'ttm_income_statement',
    'ttm_cash_flow',
    'economic_calendar',
    'price_daily',
    'company_profile'
]

for table in tables_to_check:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f'{table}: {count} rows')

cur.close()
conn.close()
