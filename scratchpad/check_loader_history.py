#!/usr/bin/env python3
from utils.db.context import DatabaseContext
from datetime import datetime

db = DatabaseContext('read')
with db as cur:
    # Check data_loader_runs for metrics loaders
    print('=== METRICS LOADERS EXECUTION HISTORY ===')
    cur.execute('''
        SELECT loader_name, status, started_at, completed_at
        FROM data_loader_runs
        WHERE loader_name IN ('quality_metrics', 'growth_metrics', 'value_metrics', 'stability_metrics', 'momentum_metrics', 'positioning_metrics', 'stock_scores')
        ORDER BY started_at DESC
        LIMIT 30
    ''')
    rows = cur.fetchall()
    if rows:
        for row in rows:
            loader = row['loader_name']
            status = row['status']
            started = row['started_at']
            print(f'{loader}: {status} (started {started})')
    else:
        print('NO METRICS LOADER EXECUTIONS FOUND IN DATABASE')

    # Check how many total data loaders exist
    print('\n=== ALL LOADER TYPES IN DATABASE ===')
    cur.execute('''
        SELECT DISTINCT loader_name
        FROM data_loader_runs
        ORDER BY loader_name
    ''')
    rows = cur.fetchall()
    print(f'Total distinct loaders: {len(rows)}')
    for row in rows[:15]:
        print(f'  - {row["loader_name"]}')
    if len(rows) > 15:
        print(f'  ... and {len(rows)-15} more')
