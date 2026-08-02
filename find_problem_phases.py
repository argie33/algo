#!/usr/bin/env python3
"""Find problem phases in degraded/halted runs."""

import json
from utils.db.context import DatabaseContext

print("\n" + "="*100)
print("PROBLEM PHASES IN DEGRADED/HALTED RUNS")
print("="*100 + "\n")

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT run_id, overall_status, phase_results
        FROM orchestrator_execution_log
        WHERE overall_status IN ('halted', 'degraded')
        ORDER BY created_at DESC
        LIMIT 15
    ''')

    problem_runs = cur.fetchall()

for run_id, overall_status, phase_results in problem_runs:
    if not isinstance(phase_results, list):
        continue

    problem_phases = []
    for phase in phase_results:
        if not isinstance(phase, dict):
            continue

        status = phase.get('status', '')
        if status in ('error', 'halted', 'halt', 'degraded', 'alert'):
            problem_phases.append(phase)

    if problem_phases:
        print(f"\nRun: {run_id} | Overall: {overall_status}")
        print(f"{'-'*80}")

        for phase in problem_phases:
            phase_num = phase.get('phase', '?')
            name = phase.get('name', '?')
            status = phase.get('status', '?')
            summary = phase.get('summary', '')

            print(f"  Phase {phase_num} ({name}): {status}")
            if summary:
                print(f"    {summary}")

print(f"\n{'='*100}\n")
