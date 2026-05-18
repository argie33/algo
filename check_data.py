#!/usr/bin/env python3
import psycopg2
import os

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cur = conn.cursor()

tables = [
    ('stock_scores', 'Swing trader scores'),
    ('buy_sell_daily', 'Buy/sell signals'),
    ('market_health_daily', 'Market health'),
    ('sector_ranking', 'Sector ranking'),
    ('price_daily', 'Price data'),
]

print("Checking data freshness for API endpoints...\n")
for table, desc in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count:,} rows - {desc}")
    except Exception as e:
        print(f"  {table}: ERROR - {str(e)[:50]}")

# Close failed transaction
cur.close()
conn.rollback()
cur = conn.cursor()

print("\nChecking /api/scores endpoint data...")
try:
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    print(f"  stock_scores: {cur.fetchone()[0]} rows")
except:
    # Try to get schema
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'stock_scores'")
    cols = cur.fetchall()
    if cols:
        print("  stock_scores columns: " + ", ".join(f"{c[0]}({c[1]})" for c in cols[:5]))

cur.close()
conn.close()
