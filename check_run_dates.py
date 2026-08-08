#!/usr/bin/env python3
from utils.db.connection import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Check run_date values in orchestrator_execution_log
cur.execute('''
SELECT DISTINCT run_date, COUNT(*) as count
FROM orchestrator_execution_log
WHERE started_at > now() - interval '3 days'
GROUP BY run_date
ORDER BY run_date DESC
''')

print('=== run_date values in orchestrator_execution_log ===')
for run_date, count in cur.fetchall():
    print(f'{run_date}: {count} runs')

print('\n=== Check for NULL run_date ===')
cur.execute('SELECT COUNT(*) FROM orchestrator_execution_log WHERE run_date IS NULL')
null_count = cur.fetchone()[0]
print(f'Rows with NULL run_date: {null_count}')

print('\n=== Sample run details ===')
cur.execute('''
SELECT run_id, run_date, started_at, DATE(started_at) as logged_date
FROM orchestrator_execution_log
WHERE run_id LIKE 'LOCAL-AFTERNOON%'
ORDER BY started_at DESC
LIMIT 5
''')

for run_id, run_date, started_at, logged_date in cur.fetchall():
    match = "✓" if run_date == logged_date else "✗ MISMATCH"
    print(f'{match} {run_id:50} run_date={run_date} logged_date={logged_date}')

cur.close()
conn.close()
