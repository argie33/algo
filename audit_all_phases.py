#!/usr/bin/env python3
from utils.db import DatabaseContext
import json

print('=== ALL PHASES IN LATEST RUN ===\n')

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
            print(f'Total phases: {len(phases)}')
            print()
            for phase in phases:
                phase_num = phase.get('phase')
                phase_name = phase.get('name')
                status = phase.get('status')
                summary = phase.get('summary')
                result = phase.get('result')

                print(f'Phase {phase_num}: {phase_name} ({status})')
                print(f'  Summary: {summary}')

                if result:
                    if isinstance(result, dict):
                        print(f'  Result keys: {list(result.keys())}')
                        if 'qualified_trades' in result:
                            trades = result['qualified_trades']
                            if isinstance(trades, list):
                                print(f'  Qualified trades: {len(trades)}')
                                if len(trades) > 0:
                                    print(f'    First trade: {trades[0]}')
                    elif isinstance(result, list):
                        print(f'  Result is list with {len(result)} items')
                print()
        except Exception as e:
            print(f'Error: {e}')
            import traceback
            traceback.print_exc()
