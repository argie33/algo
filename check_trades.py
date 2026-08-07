#!/usr/bin/env python3
from utils.db.connection import get_db_connection

with get_db_connection() as conn:
    cur = conn.cursor()

    # Check the old closed trades - do they have exit_price?
    cur.execute('''
        SELECT symbol, status, quantity, entry_price, exit_price, exit_reason FROM algo_trades
        WHERE symbol IN ('EAT', 'MSFT', 'DAC', 'ECPG', 'MCK')
        AND created_at < '2026-08-07 03:04:00'
        ORDER BY created_at DESC LIMIT 5;
    ''')

    rows = cur.fetchall()
    print('Old closed trades:')
    for symbol, status, qty, entry_price, exit_price, exit_reason in rows:
        print(f'{symbol:8} status={status:8} qty={qty:>8.0f}')
        print(f'  entry=${float(entry_price):>8.2f} exit=${float(exit_price) if exit_price else None:>8}')
        print(f'  reason={exit_reason[:60]}')
        print()
