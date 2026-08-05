#!/usr/bin/env python3
import sys
import json
from pathlib import Path

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get runs with errors
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            run_id,
            run_date,
            started_at,
            phase_results,
            halt_reason
        FROM orchestrator_execution_log
        WHERE phase_results IS NOT NULL
          AND phase_results::text LIKE '%errors%'
          OR phase_results::text LIKE '%error%'
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    rows = cur.fetchall()
    print(f'Runs with errors: {len(rows)}\n')

    for row in rows:
        print(f"Run: {row['run_id']}")
        print(f"Date: {row['run_date']}, Time: {row['started_at'].strftime('%H:%M:%S')}")

        phase_results = json.loads(row['phase_results']) if isinstance(row['phase_results'], str) else row['phase_results']

        for phase in phase_results:
            status = phase.get('status', '')
            if 'error' in status.lower() or 'error' in phase.get('summary', '').lower():
                print(f"\n  Phase {phase.get('phase', '?')} ({phase.get('name', '?')}): {status}")
                print(f"  Summary: {phase.get('summary', '')}")

        if row['halt_reason']:
            print(f"  Halt reason: {row['halt_reason']}")
        print()
