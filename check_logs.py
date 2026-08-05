#!/usr/bin/env python3
import sys
from pathlib import Path

# Setup path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Load env
from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get the most recent orchestrator runs
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            run_id,
            phase,
            status,
            error_message,
            created_at
        FROM orchestrator_execution_log
        ORDER BY created_at DESC
        LIMIT 150
    ''')

    rows = cur.fetchall()
    print(f'Total rows: {len(rows)}\n')

    # Group by run_id to see which runs failed
    run_status = {}
    for row in rows:
        run_id = row['run_id']
        if run_id not in run_status:
            run_status[run_id] = []
        run_status[run_id].append(row)

    # Show each run's phases
    for run_id in sorted(run_status.keys(), reverse=True)[:5]:
        run_rows = run_status[run_id]
        latest_ts = run_rows[0]['created_at']
        print(f"\n=== Run {run_id} ({latest_ts}) ===")
        for row in sorted(run_rows, key=lambda r: r['phase']):
            phase = row['phase']
            status = row['status']
            err = row['error_message']
            ts = str(row['created_at'])[:19] if row['created_at'] else 'NULL'
            if err:
                print(f"  Phase {phase:2} | {status:10} | ERROR: {err[:120]}")
            else:
                print(f"  Phase {phase:2} | {status:10} | OK")
