#!/usr/bin/env python3
import logging
logging.basicConfig(level=logging.WARNING)
from utils.db.context import DatabaseContext

with DatabaseContext(role='read') as ctx:
    cursor = ctx.connection.cursor()

    # Check schema
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'data_loader_status'
        ORDER BY ordinal_position
    """)
    print('data_loader_status columns:')
    for col, dtype in cursor.fetchall():
        print(f'  {col}: {dtype}')

    # Get actual data
    cursor.execute('SELECT * FROM data_loader_status WHERE table_name = \'price_daily\' LIMIT 1')
    result = cursor.fetchone()
    if result:
        print('\nActual data:')
        print(f'  {result}')

    # Check last few dates in price_daily
    cursor.execute("""
        SELECT date, COUNT(DISTINCT symbol) as symbols_count
        FROM price_daily
        WHERE date >= '2026-07-27'
        GROUP BY date
        ORDER BY date DESC
    """)
    print('\nPRICE DATA BY DATE:')
    for date, count in cursor.fetchall():
        print(f'  {date}: {count} symbols')

    cursor.close()
