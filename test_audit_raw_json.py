#!/usr/bin/env python3
from utils.db import DatabaseContext
import json

print('=== RAW PHASE RESULTS ARRAY ===\n')

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT phase_results
        FROM orchestrator_execution_log
        WHERE run_id = 'RUN-2026-07-06-172110'
    ''')
    row = cur.fetchone()
    if row:
        results_raw = row[0] if isinstance(row, tuple) else row['phase_results']
        print('Type:', type(results_raw))
        print('\nRaw JSON string (first 500 chars):')
        results_str = str(results_raw)
        print(results_str[:500])

        print('\n\nParsed as JSON:')
        try:
            phases = json.loads(results_raw) if isinstance(results_raw, str) else results_raw
            print(f'Type after parse: {type(phases)}')
            print(f'Length: {len(phases) if isinstance(phases, list) else "N/A"}')

            # Print each phase's phase and name fields
            for i, phase in enumerate(phases):
                phase_num = phase.get('phase')
                name = phase.get('name')
                print(f'  [{i}] phase={phase_num}, name={name}')
        except Exception as e:
            print(f'Error: {e}')
