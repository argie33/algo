#!/usr/bin/env python3
"""Check recent orchestrator execution logs."""

from utils.db.context import DatabaseContext
import json

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT run_id, overall_status, phase_results, created_at
        FROM orchestrator_execution_log
        ORDER BY created_at DESC
        LIMIT 10
    ''')

    for row in cur.fetchall():
        run_id, overall_status, phase_results, created_at = row
        print(f'\n{"="*80}')
        print(f'Run: {run_id}')
        print(f'Overall Status: {overall_status}')
        print(f'Timestamp: {created_at}')
        print(f'{"="*80}')

        if phase_results:
            try:
                phases = json.loads(phase_results)
                for p in phases:
                    if isinstance(p, dict):
                        phase_num = p.get('phase_num', '?')
                        status = p.get('status', '?')
                        info = p.get('info', '')
                        print(f'Phase {phase_num}: {status}' + (f' - {info}' if info else ''))
            except Exception as e:
                print(f'Error parsing phases: {e}')
