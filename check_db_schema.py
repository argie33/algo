#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

os.chdir('C:\\Users\\arger\\code\\algo')
load_dotenv('.env.local')

conn = psycopg2.connect('host=localhost user=postgres password=bed0elAn dbname=stocks')
cur = conn.cursor()

# Get all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = cur.fetchall()
print(f"Found {len(tables)} tables:\n")
for t in tables:
    print(f"  {t[0]}")

# Check for stock_symbols table specifically
print("\n--- Stock Symbols table ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'stock_symbols'
    ORDER BY ordinal_position
""")
cols = cur.fetchall()
if cols:
    for c in cols:
        print(f"  {c[0]}: {c[1]}")
else:
    print("  Table not found")

# Check what's actually being queried
print("\n--- Checking for 'security_name' column ---")
cur.execute("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE column_name LIKE '%security%' OR column_name LIKE '%name%'
    ORDER BY table_name
""")
cols = cur.fetchall()
if cols:
    for c in cols[:20]:
        print(f"  {c[0]}.{c[1]}")
else:
    print("  Not found")

conn.close()
