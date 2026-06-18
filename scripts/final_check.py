#!/usr/bin/env python3
from utils.db.context import DatabaseContext


with DatabaseContext('read') as cur:
    cur.execute("SELECT COUNT(*) as total, MAX(date) as latest FROM price_daily WHERE date >= '2026-06-15'")
    row = cur.fetchone()
    print(f'Price data >= 2026-06-15: {row[0]} rows, Latest: {row[1]}')

    cur.execute("SELECT date, COUNT(*) FROM price_daily WHERE date >= '2026-06-15' GROUP BY date ORDER BY date")
    print('\nBreakdown by date:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]} rows')
