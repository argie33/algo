#!/usr/bin/env python3
from utils.db import DatabaseContext
import json

print('=== CHECKING PHASE 7 EXECUTION OUTPUT ===\n')

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
                if phase_num == '7':
                    status = phase.get('status')
                    summary = phase.get('summary')
                    print('Phase 7 Result:')
                    print('  Status: ' + str(status))
                    print('  Summary: ' + str(summary))

                    # Check if there's a detailed result
                    if 'result' in phase:
                        result = phase['result']
                        print('  Result type: ' + str(type(result)))
                        if isinstance(result, dict):
                            print('  Result keys: ' + str(list(result.keys())))
                            print('  Result: ' + str(result)[:500])
        except Exception as e:
            print('Error: ' + str(e))

print('\n=== CHECK PHASE 8 EXPECTED INPUT ===\n')
with DatabaseContext('read') as cur:
    # Check if Phase 8 is receiving qualified_trades
    cur.execute('''
        SELECT COUNT(*)
        FROM buy_sell_daily
        WHERE date = '2026-07-06' AND signal_type = 'BUY'
    ''')
    row = cur.fetchone()
    buy_signal_count = row[0] if isinstance(row, tuple) else row[0]
    print('BUY signals in buy_sell_daily: ' + str(buy_signal_count))
