#!/usr/bin/env python3
"""Check position and portfolio state."""

from utils.db import DatabaseContext

with DatabaseContext('read') as cur:
    # Check position status
    cur.execute('SELECT status, COUNT(*) FROM algo_positions GROUP BY status')
    print('POSITION STATUS DISTRIBUTION:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]}')

    # Check latest portfolio snapshot
    cur.execute('''
        SELECT snapshot_date, portfolio_value, num_positions, cash
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    ''')
    row = cur.fetchone()
    if row:
        print(f'\nLATEST PORTFOLIO SNAPSHOT:')
        print(f'  Date: {row[0]}')
        print(f'  Value: ${row[1]:,.2f}')
        print(f'  Positions: {row[2]}')
        print(f'  Cash: ${row[3]:,.2f}')

    # Check if there are any halted positions or issues
    cur.execute('SELECT COUNT(*) FROM algo_positions WHERE status = %s', ('halted',))
    halted_count = cur.fetchone()[0]
    if halted_count > 0:
        print(f'\nWARNING: {halted_count} HALTED positions')
        cur.execute('SELECT symbol FROM algo_positions WHERE status = %s LIMIT 5', ('halted',))
        for row in cur.fetchall():
            print(f'  {row[0]}')

    # Check trades over last few days
    cur.execute('''
        SELECT DATE(created_at), action_type, COUNT(*)
        FROM algo_metrics_daily
        WHERE action_type IN ('entry', 'exit')
        AND created_at >= NOW() - INTERVAL '7 days'
        GROUP BY DATE(created_at), action_type
        ORDER BY DATE(created_at) DESC, action_type
    ''')
    print('\nRECENT TRADES:')
    for row in cur.fetchall():
        print(f'  {row[0]}: {row[1]}s = {row[2]}')
