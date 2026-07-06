#!/usr/bin/env python3
from utils.db.context import DatabaseContext

db = DatabaseContext('read')
with db as cur:
    # Check orchestrator runs
    print('=== ORCHESTRATOR RUNS (LAST 5) ===')
    cur.execute('''
        SELECT run_id, phase, status, started_at, completed_at
        FROM algo_orchestrator_runs
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)

    # Check data loader runs
    print('\n=== DATA LOADER RUNS (LAST 10) ===')
    cur.execute('''
        SELECT loader_name, status, rows_loaded, started_at, completed_at
        FROM data_loader_runs
        ORDER BY started_at DESC
        LIMIT 10
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)

    # Check quality_metrics
    print('\n=== QUALITY METRICS COUNT ===')
    cur.execute('SELECT COUNT(*) as count, MAX(updated_at) as latest FROM quality_metrics')
    rows = cur.fetchall()
    for row in rows:
        print(row)

    # Check growth_metrics
    print('\n=== GROWTH METRICS COUNT ===')
    cur.execute('SELECT COUNT(*) as count, MAX(updated_at) as latest FROM growth_metrics')
    rows = cur.fetchall()
    for row in rows:
        print(row)
