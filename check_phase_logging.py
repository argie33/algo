#!/usr/bin/env python3
"""Check if phase results are properly logged in execution tracker."""

from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT run_id, overall_status, phase_results
        FROM orchestrator_execution_log
        WHERE run_date = '2026-07-30'
        ORDER BY started_at DESC
        LIMIT 10
    ''')

    for row in cur.fetchall():
        run_id, status, phase_results = row
        phases_count = len(phase_results) if phase_results else 0
        print(f'Run: {run_id}')
        print(f'  Status: {status}')
        print(f'  Phases logged: {phases_count}')
        if phase_results:
            for i, phase in enumerate(phase_results, 1):
                phase_name = phase.get('name', '?')
                phase_status = phase.get('status', '?')
                print(f'    Phase {i}: {phase_name} = {phase_status}')
        else:
            print('    *** EMPTY - NO PHASES LOGGED ***')
        print()
