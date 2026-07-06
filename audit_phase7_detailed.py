#!/usr/bin/env python3
from utils.db import DatabaseContext
import json

print('=== PHASE 7 RESULT DATA IN DETAIL ===\n')

with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT phase_results
        FROM orchestrator_execution_log
        WHERE run_id = 'RUN-2026-07-06-172110'
    ''')
    row = cur.fetchone()
    if row:
        results_raw = row[0] if isinstance(row, tuple) else row['phase_results']
        try:
            phases = json.loads(results_raw) if isinstance(results_raw, str) else results_raw
            for phase in phases:
                phase_num = phase.get('phase')
                if phase_num == '7' or phase_num == 7:
                    print('Phase 7 Full Result:')
                    print(json.dumps(phase, indent=2))

                    # Analyze the result data
                    result = phase.get('result')
                    if isinstance(result, dict):
                        qual_trades = result.get('qualified_trades')
                        print(f'\nQualified trades type: {type(qual_trades)}')
                        print(f'Qualified trades count: {len(qual_trades) if isinstance(qual_trades, list) else "N/A"}')
                        if isinstance(qual_trades, list) and len(qual_trades) > 0:
                            print(f'First signal: {qual_trades[0]}')
        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()
