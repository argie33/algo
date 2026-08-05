#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from datetime import datetime

_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext

# Get recent runs
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT
            run_id,
            run_date,
            started_at,
            completed_at,
            overall_status,
            phase_results,
            halt_reason,
            summary,
            phases_completed,
            phases_halted,
            phases_errored,
            created_at
        FROM orchestrator_execution_log
        ORDER BY created_at DESC
        LIMIT 20
    ''')

    rows = cur.fetchall()
    print(f'Recent orchestrator runs: {len(rows)} runs\n')

    for row in rows:
        run_id = row['run_id']
        run_date = row['run_date']
        started_at = row['started_at']
        completed_at = row['completed_at']
        overall_status = row['overall_status']
        halt_reason = row['halt_reason']
        summary = row['summary']
        phases_done = row['phases_completed']
        phases_halted = row['phases_halted']
        phases_errored = row['phases_errored']

        print(f"{run_id} ({run_date})")
        print(f"  Time: {started_at.strftime('%H:%M:%S')} - {completed_at.strftime('%H:%M:%S') if completed_at else 'INCOMPLETE'}")
        print(f"  Status: {overall_status} | Phases: {phases_done} done, {phases_halted} halted, {phases_errored} errored")
        if halt_reason:
            print(f"  Halt: {halt_reason[:100]}")
        if summary:
            print(f"  Summary: {summary[:100]}")

        # Parse phase_results
        if row['phase_results']:
            try:
                phase_results = json.loads(row['phase_results']) if isinstance(row['phase_results'], str) else row['phase_results']
                if phase_results:
                    print(f"  Phases: {json.dumps(phase_results, indent=4)}")
            except:
                print(f"  Phase results: {row['phase_results']}")
        print()
