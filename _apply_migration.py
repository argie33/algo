#!/usr/bin/env python3
from utils.db import DatabaseContext

sql = open('migrations/1010_add_sql_interval_configuration.sql').read()
# Remove comments
sql_lines = [line for line in sql.split('\n') if not line.strip().startswith('--')]
sql_clean = '\n'.join(sql_lines)

try:
    with DatabaseContext('write') as cur:
        cur.execute(sql_clean)
    print("[OK] Migration 1010 applied successfully")
    print("     13 new configuration keys added to algo_config table")
except Exception as e:
    print(f"[ERROR] {e}")
