#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='postgres',
    user='stocks',
    password='stocks'
)
cur = conn.cursor()
cur.execute("SELECT datname FROM pg_database WHERE datname LIKE 'stocks%' ORDER BY datname")
dbs = cur.fetchall()
print('Databases:')
for db in dbs:
    print(f'  {db[0]}')
cur.close()
conn.close()
