#!/usr/bin/env python
"""Check if execution_duration_sec is populated in data_loader_status."""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'algo')
)

with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute('''
        SELECT COUNT(*) as total,
               COUNT(execution_duration_sec) as with_duration,
               COUNT(CASE WHEN execution_duration_sec IS NULL THEN 1 END) as null_duration
        FROM data_loader_status
    ''')
    counts = cur.fetchone()
    total = counts['total']
    with_dur = counts['with_duration']
    null_dur = counts['null_duration']

    print(f'Summary:')
    print(f'  Total loaders: {total}')
    print(f'  With duration: {with_dur}')
    print(f'  NULL duration: {null_dur}')

    if with_dur > 0:
        print(f'\nRecent loaders WITH execution_duration_sec:')
        cur.execute('''
            SELECT table_name, execution_duration_sec, symbols_per_second, status
            FROM data_loader_status
            WHERE execution_duration_sec IS NOT NULL
            ORDER BY execution_completed DESC
            LIMIT 5
        ''')
        rows = cur.fetchall()
        for row in rows:
            tbl = row['table_name']
            dur = row['execution_duration_sec']
            tps = row['symbols_per_second'] or 0
            status = row['status']
            print(f'  {tbl}: {dur:.1f}s, {tps:.1f}/s (status={status})')

    print(f'\nRecent loaders WITHOUT execution_duration_sec:')
    cur.execute('''
        SELECT table_name, status
        FROM data_loader_status
        WHERE execution_duration_sec IS NULL
        ORDER BY execution_completed DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        tbl = row['table_name']
        status = row['status']
        print(f'  {tbl}: (status={status})')

conn.close()
