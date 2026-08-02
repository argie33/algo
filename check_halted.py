#!/usr/bin/env python3
import os
import psycopg2
from datetime import datetime, timedelta

os.environ.update({
    'DB_HOST': 'localhost',
    'DB_PORT': '5432',
    'DB_NAME': 'stocks',
    'DB_USER': 'stocks',
    'DB_PASSWORD': 'stocks',
    'LOCAL_MODE': 'true'
})

try:
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='stocks',
        user='stocks',
        password='stocks'
    )
    cur = conn.cursor()

    # Find all halted runs in the last 10 days
    cur.execute("""SELECT run_id, overall_status, completed_at, halt_reason
                   FROM orchestrator_execution_log
                   WHERE overall_status = 'halted'
                   ORDER BY completed_at DESC
                   LIMIT 20""")

    halted = cur.fetchall()
    print(f'Found {len(halted)} halted runs:')
    print("=" * 140)
    for row in halted:
        run_id, status, completed, reason = row
        print(f'{run_id:<40} | {completed} | {reason}')

    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
