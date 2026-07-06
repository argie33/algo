#!/usr/bin/env python3
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

db = DatabaseContext('read')
with db as cur:
    print("=== CHECKING IF METRICS WERE LOADED DURING HUNG PIPELINE ===\n")

    # Check when each metrics table was last updated
    metrics_tables = ['quality_metrics', 'growth_metrics', 'value_metrics', 'stability_metrics', 'momentum_metrics', 'positioning_metrics']

    for table in metrics_tables:
        try:
            cur.execute(f'SELECT COUNT(*) as count, MAX(updated_at) as latest FROM {table}')
            row = cur.fetchone()
            if row:
                count = row['count']
                latest = row['latest']
                print(f'{table}:')
                print(f'  Count: {count}')
                print(f'  Latest update: {latest}')

                # Calculate time since last update
                if latest:
                    time_ago = (datetime.utcnow() - latest.replace(tzinfo=None)).total_seconds() / 60
                    print(f'  Time since update: {time_ago:.1f} minutes ago')
        except Exception as e:
            print(f'{table}: ERROR - {str(e)[:100]}')
        print()

    # Check stock_scores specifically
    print("STOCK_SCORES:")
    cur.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth,
               MAX(updated_at) as latest
        FROM stock_scores
    ''')
    row = cur.fetchone()
    pct = (row['with_growth'] / row['total'] * 100) if row['total'] > 0 else 0
    print(f'  Total: {row["total"]}')
    print(f'  With growth_score: {row["with_growth"]} ({pct:.1f}%)')
    print(f'  Latest update: {row["latest"]}')

    # Check data loader execution log for any errors
    print("\n=== DATA LOADER EXECUTION ERRORS ===")
    cur.execute('''
        SELECT loader_name, status, error_message, started_at
        FROM data_loader_runs
        WHERE status = 'failed'
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    if rows:
        for row in rows:
            print(f'{row["loader_name"]} FAILED at {row["started_at"]}')
            if row['error_message']:
                print(f'  Error: {row["error_message"][:200]}')
    else:
        print('No recent loader failures')
