#!/usr/bin/env python3
import psycopg2
import os

db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME', 'stocks'),
}

conn = psycopg2.connect(**db_config)
cur = conn.cursor()

# Get all tables with data
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = [t[0] for t in cur.fetchall()]

tables_with_data = []
for tbl in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {tbl}')
        count = cur.fetchone()[0]
        if count > 0:
            tables_with_data.append((tbl, count))
    except:
        pass

tables_with_data.sort(key=lambda x: x[1], reverse=True)
total_records = sum(c for _, c in tables_with_data)

print(f"\n=== Loader Progress ===")
print(f"Tables with data: {len(tables_with_data)}/{len(tables)}")
print(f"Total records loaded: {total_records:,}\n")

for tbl, count in tables_with_data[:15]:
    print(f"  {tbl}: {count:,}")

if len(tables_with_data) > 15:
    print(f"  ... and {len(tables_with_data) - 15} more tables")

conn.close()
