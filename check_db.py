import sqlite3
import os

for db in ['algo.db', 'stocks.db']:
    if not os.path.exists(db):
        print(f'{db} not found')
        continue

    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = c.fetchall()
    print(f'\n{db}:')
    for t in tables:
        print(f'  - {t[0]}')
    conn.close()
