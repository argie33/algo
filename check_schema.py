#!/usr/bin/env python3
from utils.db import DatabaseContext

# Check algo_config schema
with DatabaseContext('read') as cur:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='algo_config' ORDER BY ordinal_position")
    cols = cur.fetchall()
    print('algo_config columns:', [r[0] if isinstance(r, (tuple, list)) else r.get('column_name') for r in cols])

# Get all config values
with DatabaseContext('read') as cur:
    cur.execute('SELECT * FROM algo_config LIMIT 10')
    rows = cur.fetchall()
    if rows and isinstance(rows[0], dict):
        print('\nalgo_config sample:')
        for row in rows[:5]:
            print(f"  {row}")
