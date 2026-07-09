#!/usr/bin/env python3
from utils.db.context import DatabaseContext

db = DatabaseContext('read')
with db as cur:
    # Check algo_portfolio_snapshots schema
    print('=== algo_portfolio_snapshots SCHEMA ===')
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_portfolio_snapshots'
        ORDER BY ordinal_position
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'  {row["column_name"]}: {row["data_type"]}')

    # Check data in portfolio snapshots
    print('\n=== PORTFOLIO SNAPSHOTS (Last 3) ===')
    cur.execute('SELECT * FROM algo_portfolio_snapshots ORDER BY created_at DESC LIMIT 3')
    rows = cur.fetchall()
    for i, row in enumerate(rows):
        print(f'\nSnapshot {i+1}:')
        for key in row.keys():
            val = row[key]
            if val is not None and len(str(val)) > 100:
                val = str(val)[:100] + '...'
            print(f'  {key}: {val}')

    # Check open positions to see actual portfolio state
    print('\n=== OPEN POSITIONS SUMMARY ===')
    cur.execute('''
        SELECT COUNT(*) as count,
               SUM(quantity) as total_shares,
               SUM(position_value) as total_value
        FROM algo_positions
        WHERE is_open = TRUE
    ''')
    row = cur.fetchone()
    print(f'Open positions: {row["count"]}')
    print(f'Total shares: {row["total_shares"]}')
    print(f'Total value: {row["total_value"]}')

    # Check if Phase 9 is checking for missing fields
    print('\n=== RECENT ORCHESTRATOR PHASE RESULTS ===')
    cur.execute('''
        SELECT run_id, phase_results, summary
        FROM orchestrator_execution_log
        WHERE overall_status = 'error' AND started_at >= CURRENT_DATE - get_interval_sql('1d')
        LIMIT 1
    ''')
    row = cur.fetchone()
    if row:
        import json
        try:
            results = json.loads(row['phase_results']) if row['phase_results'] else {}
            print(f'Run {row["run_id"]}:')
            for key, val in results.items():
                print(f'  {key}: {val}')
        except:
            print(f'  {row["phase_results"]}')
        print(f'\nSummary: {row["summary"]}')
