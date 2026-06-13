#!/usr/bin/env python3
import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=os.environ['DB_PORT'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME']
)
cur = conn.cursor()
cur.execute("SELECT key, value FROM algo_config WHERE key = 'phase1_min_symbol_count'")
row = cur.fetchone()
print(f"Database phase1_min_symbol_count: {row[1] if row else 'NOT FOUND'}")
conn.close()
