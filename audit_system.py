#!/usr/bin/env python3
"""Comprehensive system audit for bulletproofness."""

from utils.db import DatabaseContext

print('=' * 70)
print('COMPREHENSIVE SYSTEM AUDIT')
print('=' * 70)

with DatabaseContext('read') as cur:
    # 1. Check loader locks
    print('\n[1] LOADER LOCKS STATUS')
    cur.execute('''
        SELECT loader_name, locked_at, expires_at, locked_by,
               EXTRACT(EPOCH FROM (NOW() - locked_at)) as held_sec
        FROM loader_execution_locks
        ORDER BY held_sec DESC
    ''')
    locks = cur.fetchall()
    if locks:
        print(f'  {len(locks)} active locks:')
        for name, locked_at, expires_at, locked_by, held_sec in locks:
            print(f'    {name}: held {held_sec:.0f}s')
    else:
        print('  ✓ No stale locks')

    # 2. Check halt flag
    print('\n[2] HALT FLAG STATUS')
    cur.execute('SELECT COUNT(*) FROM halt_flags WHERE status = true')
    halt_count = cur.fetchone()[0]
    if halt_count > 0:
        print(f'  ⚠ WARNING: {halt_count} halt(s) active')
        cur.execute('SELECT reason, SET AT FROM halt_flags WHERE status = true')
        for reason, set_at in cur.fetchall():
            print(f'    - {reason}')
    else:
        print('  ✓ No halts active')

    # 3. Check open positions
    print('\n[3] OPEN POSITIONS')
    cur.execute('SELECT COUNT(*), COALESCE(SUM(position_value), 0) FROM algo_positions WHERE status = %s', ('open',))
    count, total_value = cur.fetchone()
    print(f'  {count} positions, value: ${total_value:,.2f}')

    # 4. Check recent orchestrator runs
    print('\n[4] RECENT ORCHESTRATOR RUNS (last 24h)')
    cur.execute('''
        SELECT run_id, overall_status, started_at
        FROM orchestrator_execution_log
        WHERE started_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    for run_id, status, started_at in cur.fetchall():
        print(f'  {run_id[-20:]}: {status}')

    # 5. Check for data quality issues
    print('\n[5] DATA QUALITY CHECK')
    cur.execute('''
        SELECT COUNT(*) FROM algo_positions
        WHERE status = 'open' AND (
            avg_entry_price IS NULL OR
            stop_loss_price IS NULL OR
            current_price IS NULL OR
            quantity IS NULL
        )
    ''')
    issue_count = cur.fetchone()[0]
    if issue_count > 0:
        print(f'  ⚠ WARNING: {issue_count} position(s) with missing fields')
    else:
        print('  ✓ All position data complete')

print('\n' + '=' * 70)
