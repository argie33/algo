#!/usr/bin/env python3
from utils.db import DatabaseContext

print('=== CIRCUIT BREAKERS & GATES ===')

with DatabaseContext('read') as cur:
    # Check circuit breaker status
    cur.execute('SELECT config_key, config_value FROM algo_config WHERE config_key LIKE \'%halt%\' OR config_key LIKE \'%break%\' OR config_key LIKE \'%max%positions%\'')
    configs = cur.fetchall()
    print('Circuit Breaker/Gate Configs:')
    for row in configs:
        if isinstance(row, dict):
            print(f"  {row.get('config_key')}: {row.get('config_value')}")
        elif isinstance(row, (tuple, list)) and len(row) >= 2:
            print(f"  {row[0]}: {row[1]}")

    # Check recent trades to understand why none since Jun 15
    print('\n=== RECENT SIGNALS (stock_scores) ===')
    cur.execute('''
        SELECT COUNT(*), MAX(updated_at)
        FROM stock_scores
        WHERE composite_score > 60 AND data_completeness >= 70
    ''')
    row = cur.fetchone()
    if row:
        count = row[0] if isinstance(row, (tuple, list)) else 0
        updated = row[1] if isinstance(row, (tuple, list)) else None
        print(f'High-quality signals available: {count}')
        print(f'Last updated: {updated}')

    # Check if there are any BUY signals
    print('\n=== BUY/SELL SIGNALS ===')
    cur.execute('''
        SELECT COUNT(*), MAX(date)
        FROM buy_sell_daily
        WHERE signal = 'BUY'
    ''')
    row = cur.fetchone()
    if row:
        buy_count = row[0] if isinstance(row, (tuple, list)) else 0
        buy_date = row[1] if isinstance(row, (tuple, list)) else None
        print(f'BUY signals in buy_sell_daily: {buy_count}, latest: {buy_date}')

# Check what the current position limits are
print('\n=== POSITION LIMITS & HALTS ===')
with DatabaseContext('read') as cur:
    # Check algo_config for position limits and halt flags
    cur.execute('''
        SELECT config_key, config_value
        FROM algo_config
        WHERE config_key IN (
            'max_new_positions',
            'halt_new_entries',
            'execution_mode',
            'phase7_entry_gate',
            'phase8_entry_gate'
        )
        ORDER BY config_key
    ''')
    configs = cur.fetchall()
    for row in configs:
        if isinstance(row, dict):
            k = row.get('config_key')
            v = row.get('config_value')
        elif isinstance(row, (tuple, list)):
            k = row[0]
            v = row[1]
        else:
            continue
        print(f'{k:30s}: {v}')

print('\n=== PHASE 8 EXECUTION LOG (recent entries) ===')
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT phase_results
        FROM orchestrator_execution_log
        WHERE overall_status IN ('success', 'ok')
        ORDER BY started_at DESC
        LIMIT 1
    ''')
    row = cur.fetchone()
    if row:
        import json
        results = row[0] if isinstance(row, (tuple, list)) else row.get('phase_results')
        if results:
            try:
                phase_data = json.loads(results) if isinstance(results, str) else results
                if isinstance(phase_data, dict) and '8' in phase_data:
                    phase8 = phase_data['8']
                    print(f'Last successful Phase 8: {json.dumps(phase8, indent=2)}')
                else:
                    print('Phase 8 data not found in last successful run')
            except:
                print('Could not parse phase results')
