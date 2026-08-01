#!/usr/bin/env python3
"""Check if supposedly fixed positions are actually closed."""

from utils.db import DatabaseContext

problem_symbols = ['PFIS', 'GSL', 'FRT', 'FVCB', 'SEIC', 'EAT', 'HIG', 'MUFG', 'SUI', 'LTH', 'FBP', 'KO', 'NDAQ', 'DRH', 'THG', 'ECO', 'JLL']

with DatabaseContext('read') as cur:
    print('STATUS OF "SUPPOSEDLY FIXED" POSITIONS:')
    print('=' * 70)

    still_open = []
    for symbol in problem_symbols:
        cur.execute('SELECT symbol, status FROM algo_positions WHERE symbol = %s', (symbol,))
        row = cur.fetchone()
        if row:
            status = row[1]
            mark = ' ✓ CLOSED' if status == 'closed' else ' ⚠️  STILL OPEN'
            print(f'{row[0]:6} | {status:8} {mark}')
            if status == 'open':
                still_open.append(symbol)
        else:
            print(f'{symbol:6} | NOT FOUND')

    print(f'\n⚠️  CRITICAL: {len(still_open)} positions still OPEN that should be CLOSED:')
    for symbol in still_open:
        print(f'  - {symbol}')

    print('\n\nCURRENT OPEN POSITIONS:')
    print('=' * 70)
    cur.execute('SELECT symbol FROM algo_positions WHERE status = %s ORDER BY symbol', ('open',))
    all_open = cur.fetchall()
    for row in all_open:
        print(f'  {row[0]}')
    print(f'\nTotal: {len(all_open)} open positions')
