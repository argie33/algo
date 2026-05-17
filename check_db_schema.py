#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

os.chdir('C:\\Users\\arger\\code\\algo')
load_dotenv('.env.local')

db_password = os.getenv('DB_PASSWORD', 'postgres')
conn = psycopg2.connect(f'host=localhost user=postgres password={db_password} dbname=stocks')
cur = conn.cursor()

# Get all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = cur.fetchall()
logger.info(f"Found {len(tables)} tables:\n")
for t in tables:
    logger.info(f"  {t[0]}")

# Check for stock_symbols table specifically
logger.info("\n--- Stock Symbols table ---")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'stock_symbols'
    ORDER BY ordinal_position
""")
cols = cur.fetchall()
if cols:
    for c in cols:
        logger.info(f"  {c[0]}: {c[1]}")
else:
    logger.info("  Table not found")

# Check what's actually being queried
logger.info("\n--- Checking for 'security_name' column ---")
cur.execute("""
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE column_name LIKE '%security%' OR column_name LIKE '%name%'
    ORDER BY table_name
""")
cols = cur.fetchall()
if cols:
    for c in cols[:20]:
        logger.info(f"  {c[0]}.{c[1]}")
else:
    logger.info("  Not found")

conn.close()
