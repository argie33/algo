#!/usr/bin/env python3
import os
import psycopg2

cfg = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "password"),
    "dbname": os.environ.get("DB_NAME", "stocks"),
}

conn = psycopg2.connect(**cfg)
cur = conn.cursor()

print("=== price_daily table schema ===")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'price_daily'
    ORDER BY ordinal_position
""")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== aaii_sentiment table schema ===")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'aaii_sentiment'
    ORDER BY ordinal_position
""")
results = cur.fetchall()
if results:
    for row in results:
        print(f"  {row[0]}: {row[1]}")
else:
    print("  Table does not exist")

print("\n=== fear_greed_index table schema ===")
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'fear_greed_index'
    ORDER BY ordinal_position
""")
results = cur.fetchall()
if results:
    for row in results:
        print(f"  {row[0]}: {row[1]}")
else:
    print("  Table does not exist")

cur.close()
conn.close()
