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
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = cur.fetchall()
print(f'Total tables: {len(tables)}')
for t in sorted([t[0] for t in tables]):
    print(f'  {t}')
cur.close()
conn.close()
