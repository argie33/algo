#!/usr/bin/env python3
import logging
logging.basicConfig(level=logging.WARNING)
from utils.db.context import DatabaseContext

with DatabaseContext(role='read') as ctx:
    cursor = ctx.connection.cursor()

    # Check the 1 symbol that has 2026-07-29 data
    cursor.execute("""
        SELECT DISTINCT symbol, date, close, data_unavailable
        FROM price_daily
        WHERE date = '2026-07-29'
        ORDER BY symbol
    """)
    print('Symbols with 2026-07-29 data:')
    for symbol, date, close, unavail in cursor.fetchall():
        print(f'  {symbol}: close=${close}, unavailable={unavail}')

    # Check if there are any price_daily rows from 2026-07-29 without proper close/open
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN close IS NULL THEN 1 END) as null_close,
               COUNT(CASE WHEN open IS NULL THEN 1 END) as null_open,
               COUNT(CASE WHEN high IS NULL THEN 1 END) as null_high
        FROM price_daily
        WHERE date = '2026-07-29'
    """)
    result = cursor.fetchone()
    if result:
        print(f'\n2026-07-29 data quality:')
        print(f'  Total rows: {result[0]}')
        print(f'  NULL close: {result[1]}')
        print(f'  NULL open: {result[2]}')
        print(f'  NULL high: {result[3]}')

    # Check the loader logs or execution history
    cursor.execute("""
        SELECT table_name, execution_started, execution_completed, symbols_loaded,
               completion_pct, status, reason, error_message
        FROM data_loader_status
        WHERE table_name = 'price_daily'
        ORDER BY execution_completed DESC
        LIMIT 3
    """)
    print('\nRecent loader runs:')
    for row in cursor.fetchall():
        print(f'  {row[0]}: {row[1]} -> {row[2]}')
        print(f'    Symbols: {row[4]}, Status: {row[5]}')
        if row[6]:
            print(f'    Reason: {row[6]}')
        if row[7]:
            print(f'    Error: {row[7]}')

    cursor.close()
