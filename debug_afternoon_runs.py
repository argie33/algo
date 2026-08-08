#!/usr/bin/env python3
from datetime import datetime, timedelta
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Check the 67 afternoon runs and see if they're in rapid succession
cur.execute('''
SELECT run_id, started_at, completed_at
FROM orchestrator_execution_log
WHERE DATE(started_at) = '2026-08-08'
AND run_id LIKE 'LOCAL-AFTERNOON%'
ORDER BY started_at
LIMIT 10
''')

print('=== First 10 AFTERNOON runs on 2026-08-08 ===')
for run_id, started_at, completed_at in cur.fetchall():
    duration = (completed_at - started_at).total_seconds() if completed_at else 0
    print(f'{started_at.strftime("%H:%M:%S.%f")} {run_id:50} duration={duration:.0f}s')

cur.execute('''
SELECT run_id, started_at
FROM orchestrator_execution_log
WHERE DATE(started_at) = '2026-08-08'
AND run_id LIKE 'LOCAL-AFTERNOON%'
ORDER BY started_at
LIMIT 1
''')
first_run = cur.fetchone()

cur.execute('''
SELECT run_id, started_at
FROM orchestrator_execution_log
WHERE DATE(started_at) = '2026-08-08'
AND run_id LIKE 'LOCAL-AFTERNOON%'
ORDER BY started_at DESC
LIMIT 1
''')
last_run = cur.fetchone()

print(f'\nFirst afternoon run:  {first_run[1].strftime("%Y-%m-%d %H:%M:%S")}')
print(f'Last afternoon run:   {last_run[1].strftime("%Y-%m-%d %H:%M:%S")}')
span = (last_run[1] - first_run[1]).total_seconds()
print(f'Time span: {span/3600:.1f} hours')

cur.close()
conn.close()
