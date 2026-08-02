#!/usr/bin/env python3
"""Inspect actual phase_results structure from degraded runs."""

import json
from utils.db.context import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT run_id, overall_status, phase_results
        FROM orchestrator_execution_log
        WHERE overall_status IN ('halted', 'degraded')
        LIMIT 3
    ''')

    for run_id, overall_status, phase_results in cur.fetchall():
        print(f"\n{'='*80}")
        print(f"Run: {run_id} | Status: {overall_status}")
        print(f"{'='*80}")

        print(f"Type of phase_results: {type(phase_results)}")
        print(f"Is list: {isinstance(phase_results, list)}")
        print(f"Is dict: {isinstance(phase_results, dict)}")

        if isinstance(phase_results, list):
            print(f"Length: {len(phase_results)}")
            if len(phase_results) > 0:
                print(f"First element type: {type(phase_results[0])}")
                print(f"First element: {json.dumps(phase_results[0], indent=2, default=str)}")
        elif isinstance(phase_results, dict):
            print(f"Keys: {list(phase_results.keys())}")
            print(f"Content: {json.dumps(phase_results, indent=2, default=str)[:500]}")
        else:
            print(f"Raw: {str(phase_results)[:200]}")
