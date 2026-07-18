#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import DictCursor

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor(cursor_factory=DictCursor)

# Check table exists and has data
cur.execute('''
    SELECT COUNT(*) as total_configs
    FROM algo_config
''')
result = cur.fetchone()
print(f'Total configs in table: {result["total_configs"]}')

# Check sample configs
cur.execute('''
    SELECT key, value, updated_at
    FROM algo_config
    ORDER BY updated_at DESC
    LIMIT 15
''')
rows = cur.fetchall()
print(f'\nLatest 15 configs:')
for row in rows:
    print(f'  {row["key"]}: {row["value"]} (updated: {row["updated_at"]})')

# Check if table is empty
if result["total_configs"] == 0:
    print("\n⚠️  WARNING: algo_config table is EMPTY!")
    print("Need to populate it with initial values.")

conn.close()
