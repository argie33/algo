#!/usr/bin/env python3
"""Check actual trade execution."""

from utils.db import DatabaseContext
from datetime import datetime, timedelta

with DatabaseContext('read') as cur:
    # Check recent actions
    cur.execute('''
        SELECT DATE(created_at), action_type, COUNT(*) as cnt
        FROM algo_metrics_daily
        WHERE action_type IN ('entry', 'exit', 'stop_loss', 'take_profit')
        AND created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at), action_type
        ORDER BY DATE(created_at) DESC, action_type
    ''')

    print('RECENT TRADE ACTIONS (Last 7 days):')
    print('=' * 60)
    for row in cur.fetchall():
        print(f'{row[0]} | {row[1]:15} | {row[2]:3} actions')

    # Check today specifically
    today = datetime.now().date()
    cur.execute('''
        SELECT action_type, COUNT(*), symbol, quantity, entry_price
        FROM algo_metrics_daily
        WHERE action_type IN ('entry', 'exit')
        AND DATE(created_at) >= %s
        GROUP BY action_type, symbol, quantity, entry_price
        ORDER BY created_at DESC
        LIMIT 20
    ''', (today,))

    print(f'\nTODAY ACTIONS ({today}):')
    print('=' * 90)
    for row in cur.fetchall():
        print(f'{row[0]:8} | {row[1]:2} | {row[2]:6} | qty={row[3]} | price={row[4]}')

    # Check position lifecycle
    print(f'\nPOSITION LIFECYCLE:')
    print('=' * 60)
    cur.execute('''
        SELECT status, COUNT(*), MIN(created_at), MAX(created_at)
        FROM algo_positions
        GROUP BY status
    ''')

    for row in cur.fetchall():
        print(f'{row[0]:10} | Count: {row[1]:3} | First: {row[2][:10]} | Last: {row[3][:10]}')

print("\nDIAGNOSIS: Are trades actually executing?")
print("=" * 60)
print("If entry count > 0: Yes, trades are executing")
print("If entry count = 0: Trades not executing (despite Phase 8 saying 'ok')")
