#!/usr/bin/env python3
from utils.db import DatabaseContext
import json

print('=== POSITION LIMITS & HALTS ===')
with DatabaseContext('read') as cur:
    # Check algo_config for position limits and halt flags
    cur.execute('''
        SELECT key, value
        FROM algo_config
        WHERE key IN (
            'max_new_positions',
            'halt_new_entries',
            'execution_mode',
            'phase7_entry_gate',
            'phase8_entry_gate'
        )
        ORDER BY key
    ''')
    configs = cur.fetchall()
    for row in configs:
        if isinstance(row, dict):
            k = row.get('key')
            v = row.get('value')
        elif isinstance(row, (tuple, list)):
            k = row[0]
            v = row[1]
        else:
            continue
        print(f'{k:30s}: {v}')

# Check recent trades to understand why none since Jun 15
print('\n=== RECENT SIGNALS (stock_scores) ===')
with DatabaseContext('read') as cur:
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
with DatabaseContext('read') as cur:
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

print('\n=== LAST SUCCESSFUL ORCHESTRATOR RUN ===')
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT started_at, overall_status, phase_results
        FROM orchestrator_execution_log
        WHERE overall_status IN ('success', 'ok')
        ORDER BY started_at DESC
        LIMIT 1
    ''')
    row = cur.fetchone()
    if row:
        started = row[0] if isinstance(row, (tuple, list)) else row.get('started_at')
        status = row[1] if isinstance(row, (tuple, list)) else row.get('overall_status')
        results_raw = row[2] if isinstance(row, (tuple, list)) else row.get('phase_results')
        print(f'Last run: {started}')
        print(f'Status: {status}')
        if results_raw:
            try:
                phase_data = json.loads(results_raw) if isinstance(results_raw, str) else results_raw
                if isinstance(phase_data, dict):
                    for phase_num in sorted(phase_data.keys(), key=lambda x: int(x) if x.isdigit() else 99):
                        phase_info = phase_data[phase_num]
                        if isinstance(phase_info, dict):
                            p_status = phase_info.get('status', 'unknown')
                            p_result = phase_info.get('result', '')
                            print(f'  Phase {phase_num}: {p_status} - {p_result}')
            except Exception as e:
                print(f'Could not parse phase results: {e}')
