#!/usr/bin/env python3
from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute("SELECT key, value FROM algo_config WHERE key LIKE '%risk%' OR key = 'max_total_invested_pct' ORDER BY key")
    for row in cur.fetchall():
        print(f'{row[0]}: {row[1]}')
