#!/usr/bin/env python3
import os
import psycopg2

os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'stocks')
os.environ.setdefault('DB_USER', 'stocks')
os.environ.setdefault('DB_PASSWORD', 'stocks')

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=os.environ['DB_PORT'],
    database=os.environ['DB_NAME'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD']
)

cursor = conn.cursor()

# Get all table names
cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
tables = [row[0] for row in cursor.fetchall()]

# Look for buy/sell signal tables
print("Buy/Sell Signal Tables:")
for t in sorted([x for x in tables if 'buy' in x.lower() or 'sell' in x.lower()]):
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    count = cursor.fetchone()[0]
    print(f"  {t}: {count:,}")

# Get all tables with row counts
print("\n\nAll Tables with > 100k rows:")
for t in sorted(tables):
    cursor.execute(f"SELECT COUNT(*) FROM {t}")
    count = cursor.fetchone()[0]
    if count > 100000:
        print(f"  {t}: {count:,}")

conn.close()
