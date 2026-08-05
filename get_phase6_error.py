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

# Get the run with Phase 6 error
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            run_id,
            run_date,
            started_at,
            phase_results
        FROM orchestrator_execution_log
        WHERE run_id = 'LOCAL-AFTERNOON-20260805-051013-124684'
    ''')

    row = cur.fetchone()
    if row:
        print(f"Run: {row['run_id']}")
        print(f"Date: {row['run_date']}, Time: {row['started_at']}\n")

        phase_results = json.loads(row['phase_results']) if isinstance(row['phase_results'], str) else row['phase_results']

        for phase in phase_results:
            if phase.get('phase') == '6':
                print(f"Phase {phase.get('phase')} ({phase.get('name')})")
                print(f"Status: {phase.get('status')}")
                print(f"Summary: {phase.get('summary')}")
                print(f"\nFull Phase Result:")
                print(json.dumps(phase, indent=2))
