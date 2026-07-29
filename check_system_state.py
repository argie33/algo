#!/usr/bin/env python3
from utils.db import DatabaseContext

print('=' * 80)
print('CURRENT SYSTEM STATE')
print('=' * 80)

# Check portfolio
try:
    with DatabaseContext('read') as cur:
        cur.execute('SELECT COUNT(*) as cnt, SUM(quantity) as total_qty FROM algo_positions WHERE status = %s', ('open',))
        row = cur.fetchone()
        print(f'\nOpen Positions: {row[0]} (total qty: {row[1]})')
except Exception as e:
    print(f'\nOpen Positions: ERROR - {e}')

# Check recent runs
try:
    with DatabaseContext('read') as cur:
        cur.execute('''SELECT run_id, overall_status, started_at FROM orchestrator_execution_log
                       ORDER BY started_at DESC LIMIT 3''')
        print('\nRecent Orchestrator Runs:')
        for row in cur.fetchall():
            print(f'  {row[0]}: {row[1]} at {row[2]}')
except Exception as e:
    print(f'\nRecent Runs: ERROR - {e}')

# Check sharpe ratio
try:
    with DatabaseContext('read') as cur:
        cur.execute('''SELECT date, rolling_sharpe_252d FROM algo_performance_daily
                       ORDER BY date DESC LIMIT 1''')
        row = cur.fetchone()
        if row:
            print(f'\nLatest Sharpe Ratio: {row[1]:.3f} (as of {row[0]})')
except Exception as e:
    print(f'\nSharpe Ratio: ERROR - {e}')

# Check exit execution status from most recent run
try:
    with DatabaseContext('read') as cur:
        cur.execute('''SELECT run_id FROM orchestrator_execution_log ORDER BY started_at DESC LIMIT 1''')
        result = cur.fetchone()
        run_id = result[0] if result else None

        if run_id:
            cur.execute('''SELECT phase_name, phase_status, phase_summary
                           FROM orchestrator_phase_log
                           WHERE run_id = %s
                           AND phase_name = %s''', (run_id, 'phase6_exit_execution'))
            row = cur.fetchone()
            if row:
                print(f'\nPhase 6 (Exit Execution) - Most Recent Run ({run_id}):')
                print(f'  Status: {row[1]}')
                print(f'  Summary: {row[2]}')
except Exception as e:
    print(f'\nPhase 6 Status: ERROR - {e}')

print('\n' + '=' * 80)
