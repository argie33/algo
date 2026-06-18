#!/usr/bin/env python3
from utils.db.context import DatabaseContext


with DatabaseContext('read') as cur:
    cur.execute("SELECT COUNT(*), MAX(date) FROM buy_sell_daily")
    row = cur.fetchone()
    print(f'buy_sell_daily - Count: {row[0]}, Latest: {row[1]}')

    if row[0] > 0:
        cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal='BUY' AND date >= DATE('2026-06-15')")
        buy_count = cur.fetchone()[0]
        print(f'BUY signals since 2026-06-15: {buy_count}')
