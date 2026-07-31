#!/usr/bin/env python3
from utils.db import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Clear the old exit errors from 2026-07-29
print('Clearing exit errors from 2026-07-29...')
cur.execute("DELETE FROM algo_exit_check_errors WHERE error_date = '2026-07-29'")
deleted = cur.rowcount
print(f'Deleted {deleted} error records')

conn.commit()

# Verify
cur.execute('SELECT COUNT(*) FROM algo_exit_check_errors')
result = cur.fetchone()
remaining = result[0] if result else 0
print(f'Remaining error records: {remaining}')

cur.close()
conn.close()
