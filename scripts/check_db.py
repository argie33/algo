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

# Count tables
cursor.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
tables = cursor.fetchone()[0]

# Count rows
cursor.execute("SELECT SUM(n_live_tup) FROM pg_stat_user_tables")
result = cursor.fetchone()
rows = result[0] if result[0] is not None else 0

print(f"Database Status:")
print(f"  Tables: {tables}")
print(f"  Total Rows: {rows:,}")

# List actual tables
cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
table_list = [row[0] for row in cursor.fetchall()]

print(f"\nAll {len(table_list)} Tables:")
for t in sorted(table_list)[:20]:
    print(f"  - {t}")
if len(table_list) > 20:
    print(f"  ... and {len(table_list) - 20} more")

# Check critical data tables
critical_tables = [
    'prices_daily',
    'technical_indicators_daily',
    'buy_sell_signals_daily',
    'financials',
    'stock_scores',
    'economic_data',
    'sector_rankings'
]

print(f"\nCritical Data Tables:")
for table in critical_tables:
    if table in table_list:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"  OK {table}: {count:,}")
    else:
        print(f"  MISSING {table}")

conn.close()
