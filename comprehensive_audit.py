#!/usr/bin/env python3
"""Comprehensive system audit."""
from utils.db import DatabaseContext
import json

print('=' * 80)
print('COMPREHENSIVE SYSTEM AUDIT')
print('=' * 80)

with DatabaseContext('read') as cur:
    # 1. ORCHESTRATOR RUNS
    print('\n1. ORCHESTRATOR RUN HISTORY (Last 10)')
    cur.execute('''
        SELECT run_id, started_at, overall_status, halt_reason
        FROM orchestrator_execution_log
        ORDER BY started_at DESC LIMIT 10
    ''')
    for i, row in enumerate(cur.fetchall()):
        run_id = row[0] if isinstance(row, tuple) else row['run_id']
        started = str(row[1])[:19] if isinstance(row, tuple) else str(row['started_at'])[:19]
        status = row[2] if isinstance(row, tuple) else row['overall_status']
        halt = row[3] if isinstance(row, tuple) else row['halt_reason']
        halt_str = f'| HALT: {halt[:30]}...' if halt else ''
        print(f'  {run_id} {started} {status:10s} {halt_str}')

    # 2. DATA LOADER STATUS
    print('\n2. CRITICAL DATA LOADERS')
    cur.execute('''
        SELECT table_name, latest_date, status, completion_pct
        FROM data_loader_status
        WHERE table_name IN ('buy_sell_daily', 'market_exposure_daily', 'stock_scores', 'positioning_metrics', 'value_metrics')
        ORDER BY table_name
    ''')
    for row in cur.fetchall():
        tname = row[0] if isinstance(row, tuple) else row['table_name']
        latest_date = str(row[1])[:10] if isinstance(row, tuple) else str(row['latest_date'])[:10]
        status = row[2] if isinstance(row, tuple) else row['status']
        comp_pct = row[3] if isinstance(row, tuple) else row['completion_pct']
        comp_str = f'{float(comp_pct):.0f}%' if comp_pct else 'N/A'
        print(f'  {tname:30s} | {latest_date} | {status:10s} | {comp_str:>5s}')

    # 3. SIGNAL & TRADE COUNTS
    print('\n3. SIGNALS & TRADES STATUS')
    cur.execute('''
        SELECT COUNT(*), COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = '2026-07-06' AND signal_type = 'BUY'
    ''')
    row = cur.fetchone()
    buy_count = row[0] if isinstance(row, tuple) else row[0]
    buy_symbols = row[1] if isinstance(row, tuple) else row[1]
    print(f'  BUY signals (2026-07-06): {buy_count} total ({buy_symbols} symbols)')

    cur.execute('''
        SELECT COUNT(*), MAX(entry_date) FROM algo_trades WHERE status = 'open'
    ''')
    row = cur.fetchone()
    open_trades = row[0] if isinstance(row, tuple) else row[0]
    last_trade_date = row[1] if isinstance(row, tuple) else row[1]
    print(f'  Open trades: {open_trades}')
    print(f'  Last trade date: {last_trade_date}')

    # 4. MARKET EXPOSURE
    print('\n4. MARKET EXPOSURE & ENTRY GATES')
    cur.execute('''
        SELECT date, exposure_tier, is_entry_allowed
        FROM market_exposure_daily
        ORDER BY date DESC LIMIT 3
    ''')
    for row in cur.fetchall():
        date_val = row[0] if isinstance(row, tuple) else row['date']
        tier = row[1] if isinstance(row, tuple) else row['exposure_tier']
        entry_ok = row[2] if isinstance(row, tuple) else row['is_entry_allowed']
        print(f'  {date_val} | {tier:30s} | Entry: {entry_ok}')

    # 5. PHASE EXECUTION DETAILS (Latest Run)
    print('\n5. LATEST RUN PHASE EXECUTION (RUN-2026-07-06-172110)')
    cur.execute('''
        SELECT phase_results FROM orchestrator_execution_log
        WHERE run_id = 'RUN-2026-07-06-172110'
    ''')
    row = cur.fetchone()
    if row:
        results_raw = row[0] if isinstance(row, tuple) else row['phase_results']
        try:
            phases = json.loads(results_raw) if isinstance(results_raw, str) else results_raw
            print(f'  Total phases: {len(phases)}')
            for phase in phases:
                phase_num = phase.get('phase')
                name = phase.get('name')
                status = phase.get('status')
                summary = phase.get('summary', '')[:50]
                print(f'    Phase {phase_num}: {name:30s} ({status:10s})')
                if 'qualified_trades' in phase.get('result', {}):
                    trades_count = len(phase['result']['qualified_trades'])
                    print(f'      → Qualified trades: {trades_count}')
        except Exception as e:
            print(f'  Error parsing phases: {e}')

    # 6. API ENDPOINT HEALTH
    print('\n6. API ENDPOINT HEALTH CHECK')
    endpoints = [
        '/api/algo/portfolio',
        '/api/algo/positions',
        '/api/algo/metrics',
        '/api/algo/scores',
    ]
    print('  (Requires running API server - check lambda or local server)')

    # 7. DATABASE TABLE ROW COUNTS
    print('\n7. CRITICAL TABLE ROW COUNTS')
    tables = [
        ('algo_trades', 'All trades'),
        ('algo_positions', 'All positions'),
        ('buy_sell_daily', 'Buy/sell signals'),
        ('stock_scores', 'Stock scores'),
    ]
    for table, desc in tables:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0] if cur.fetchone() else 0
        print(f'  {table:25s}: {count:>10,}')

    # 8. CIRCUIT BREAKER STATUS
    print('\n8. CIRCUIT BREAKER STATUS')
    cur.execute('''
        SELECT key, value FROM algo_config
        WHERE key IN ('vix_breaker_threshold', 'execution_mode', 'halt_new_entries')
    ''')
    for row in cur.fetchall():
        key = row[0] if isinstance(row, tuple) else row['key']
        val = row[1] if isinstance(row, tuple) else row['value']
        print(f'  {key:30s}: {val}')

print('\n' + '=' * 80)
