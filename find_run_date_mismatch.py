#!/usr/bin/env python3
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Find runs where run_date != DATE(started_at)
cur.execute('''
SELECT COUNT(*) as mismatched
FROM orchestrator_execution_log
WHERE DATE(started_at) != run_date
AND started_at > now() - interval '3 days'
''')

mismatched = cur.fetchone()[0]
print(f'Runs with run_date mismatch: {mismatched}')

if mismatched > 0:
    print('\n=== Examples of mismatched run_date ===')
    cur.execute('''
    SELECT run_id, run_date, started_at, DATE(started_at) as actual_date
    FROM orchestrator_execution_log
    WHERE DATE(started_at) != run_date
    AND started_at > now() - interval '3 days'
    ORDER BY started_at DESC
    LIMIT 10
    ''')

    for run_id, run_date, started_at, actual_date in cur.fetchall():
        print(f'  {run_id:50} | run_date={run_date} | started={actual_date} | TIME: {started_at.strftime("%Y-%m-%d %H:%M:%S")}')

# Check specifically for 2026-08-08 and 2026-08-07 runs
print('\n=== Afternoon runs on 2026-08-08 (by run_date) ===')
cur.execute('''
SELECT COUNT(*) FROM orchestrator_execution_log
WHERE run_id LIKE 'LOCAL-AFTERNOON%'
AND run_date = '2026-08-08'
''')
print(f'  run_date = 2026-08-08: {cur.fetchone()[0]}')

cur.execute('''
SELECT COUNT(*) FROM orchestrator_execution_log
WHERE run_id LIKE 'LOCAL-AFTERNOON%'
AND run_date = '2026-08-07'
AND DATE(started_at) = '2026-08-08'
''')
print(f'  run_date = 2026-08-07 BUT started_at on 2026-08-08: {cur.fetchone()[0]}')

cur.close()
conn.close()
