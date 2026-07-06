#!/usr/bin/env python3
from utils.db import DatabaseContext

print('=== LAST ORCHESTRATOR RUN ===')

with DatabaseContext('read') as cur:
    # Check the input JSON from the last run
    cur.execute('''
        SELECT run_id, started_at
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 1
    ''')
    row = cur.fetchone()
    if row:
        run_id = row[0] if isinstance(row, (tuple, list)) else row.get('run_id')
        started = row[1] if isinstance(row, (tuple, list)) else row.get('started_at')
        print(f'Last run: {run_id}')
        print(f'Datetime: {started}')
        print()

# Check config settings
print('=== EXECUTION CONFIG ===')
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT key, value
        FROM algo_config
        WHERE key IN ('execution_mode', 'dry_run', 'max_new_positions', 'halt_new_entries')
        ORDER BY key
    ''')
    for row in cur.fetchall():
        if isinstance(row, dict):
            k = row.get('key')
            v = row.get('value')
        else:
            k, v = row[0], row[1]
        print(f'{k}: {v}')

print('\n=== RECENT ORCHESTRATOR RUNS (parameter check) ===')
with DatabaseContext('read') as cur:
    # Check different recent runs to see if any were NOT test/dry-run
    cur.execute('''
        SELECT started_at, overall_status FROM orchestrator_execution_log
        ORDER BY started_at DESC LIMIT 5
    ''')
    for row in cur.fetchall():
        started = row[0] if isinstance(row, (tuple, list)) else row.get('started_at')
        status = row[1] if isinstance(row, (tuple, list)) else row.get('overall_status')
        is_test = 'TEST' in str(started) or status in ['test', 'dry']
        print(f'{str(started)[:19]} | {status:10s} | Test run: {is_test}')
