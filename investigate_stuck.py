from utils.database_context import DatabaseContext
from datetime import datetime, timedelta

with DatabaseContext('read') as cur:
    # Check how long loaders have been in RUNNING state
    cur.execute('''
        SELECT table_name, last_updated, EXTRACT(DAY FROM CURRENT_TIMESTAMP - last_updated) as stuck_days
        FROM data_loader_status
        WHERE status = 'RUNNING'
        ORDER BY stuck_days DESC
    ''')
    rows = cur.fetchall()
    print(f'Loaders stuck in RUNNING state:')
    print('-' * 60)
    for row in rows:
        days = int(row[2]) if row[2] else 0
        print(f'{row[0]:35} since {str(row[1])[:10]} ({days:2d} days stuck)')

    # Check execution history to see if these were actually completed
    print(f'\nChecking execution history:')
    cur.execute('''
        SELECT table_name, status, execution_completed, execution_started, created_at
        FROM data_loader_status
        WHERE table_name IN ('buy_sell_daily', 'technical_data_daily', 'signal_quality_scores')
        ORDER BY created_at DESC
        LIMIT 10
    ''')
    rows = cur.fetchall()
    for row in rows:
        completed = row[2]
        started = row[3]
        status = f'{row[1]:15}'
        if completed and started:
            duration_sec = (completed - started).total_seconds()
            print(f'{row[0]:30} {status} | duration: {duration_sec:.0f}s | {str(row[4])[:19]}')
        else:
            print(f'{row[0]:30} {status} | started: {started} completed: {completed}')
