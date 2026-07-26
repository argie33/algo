#!/usr/bin/env python3
"""Check loader execution history to find errors."""

import psycopg2

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

# Check loader_execution_history for segment loader
cur.execute("""
    SELECT loader_name, status, execution_start, COALESCE(execution_end, NOW()) as exec_end, error_message
    FROM loader_execution_history
    WHERE loader_name IN ('sec_segment_info', 'insider_transaction_velocity', 'current_reports_8k', 'dividend_data')
    ORDER BY execution_start DESC
    LIMIT 20
""")

print('Recent loader execution history:')
print('=' * 80)
for name, status, start, end, error in cur.fetchall():
    print(f'{name}: {status} (started {start})')
    if error and error.strip():
        print(f'  Error: {error[:300]}...' if len(error) > 300 else f'  Error: {error}')
    print()

# Check for stuck loaders
cur.execute("""
    SELECT loader_name, locked_at, expires_at, (NOW() > expires_at) as expired
    FROM loader_execution_locks
    ORDER BY locked_at DESC
    LIMIT 10
""")

results = cur.fetchall()
if results:
    print('\n' + '='*80)
    print('Active locks:')
    for name, locked_at, expires_at, expired in results:
        print(f'{name}: locked {locked_at}, expires {expires_at} (expired={expired})')

conn.close()
