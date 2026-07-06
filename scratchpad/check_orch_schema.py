#!/usr/bin/env python3
from utils.db.context import DatabaseContext

db = DatabaseContext('read')
with db as cur:
    # Check orchestrator_execution_log schema
    print('=== orchestrator_execution_log SCHEMA ===')
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'orchestrator_execution_log'
        ORDER BY ordinal_position
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["column_name"]}: {row["data_type"]}')

    # Check data_loader_runs schema
    print('\n=== data_loader_runs SCHEMA (if exists) ===')
    try:
        cur.execute('''
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'data_loader_runs'
            ORDER BY ordinal_position
        ''')
        rows = cur.fetchall()
        for row in rows:
            print(f'{row["column_name"]}: {row["data_type"]}')
    except:
        print("Table does not exist")

    # Check orchestrator_execution_log recent entries
    print('\n=== RECENT ORCHESTRATOR RUNS ===')
    cur.execute('''
        SELECT run_id, overall_status, phases_completed, phases_halted, phases_errored, started_at, completed_at
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)

    # Check data loader runs
    print('\n=== RECENT DATA LOADER RUNS ===')
    cur.execute('''
        SELECT loader_name, status, records_loaded, records_updated, duration_seconds, started_at
        FROM data_loader_runs
        ORDER BY started_at DESC
        LIMIT 10
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)
