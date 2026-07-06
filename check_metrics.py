#!/usr/bin/env python3
from utils.db import DatabaseContext

print('=== VALUE_METRICS DATA COVERAGE ===')

with DatabaseContext('read') as cur:
    # Check value_metrics availability
    cur.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available,
            COUNT(CASE WHEN data_unavailable = true THEN 1 END) as unavailable
        FROM value_metrics
    ''')
    row = cur.fetchone()
    total = row[0] if isinstance(row, (tuple, list)) else 0
    available = row[1] if isinstance(row, (tuple, list)) else 0
    unavailable = row[2] if isinstance(row, (tuple, list)) else 0

    coverage = (available / total * 100) if total > 0 else 0
    print(f'Total rows: {total}')
    print(f'Available (real data): {available}')
    print(f'Unavailable (marked): {unavailable}')
    print(f'Coverage: {coverage:.1f}%')
    print(f'Required: 70%')
    status = "PASS" if coverage >= 70 else "FAIL - BLOCKING ORCHESTRATOR"
    print(f'Status: {status}')

print('\n=== OTHER METRICS ===')
for table in ['growth_metrics', 'positioning_metrics', 'stability_metrics', 'quality_metrics']:
    with DatabaseContext('read') as cur:
        cur.execute(f'''
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available
            FROM {table}
        ''')
        row = cur.fetchone()
        total = row[0] if isinstance(row, (tuple, list)) else 0
        available = row[1] if isinstance(row, (tuple, list)) else 0
        coverage = (available / total * 100) if total > 0 else 0
        print(f'{table:25s}: {coverage:6.1f}% ({available}/{total})')

# Now check all positions and trades
print('\n=== POSITIONS & TRADES ===')
with DatabaseContext('read') as cur:
    cur.execute('SELECT COUNT(*), COUNT(CASE WHEN status=\'open\' THEN 1 END) FROM algo_positions_with_risk')
    row = cur.fetchone()
    total_pos = row[0] if isinstance(row, (tuple, list)) else 0
    open_pos = row[1] if isinstance(row, (tuple, list)) else 0
    print(f'Positions view: {total_pos} total, {open_pos} open')

    cur.execute('SELECT COUNT(*), COUNT(CASE WHEN status=\'open\' THEN 1 END) FROM algo_trades')
    row = cur.fetchone()
    total_trades = row[0] if isinstance(row, (tuple, list)) else 0
    open_trades = row[1] if isinstance(row, (tuple, list)) else 0
    print(f'Trades table: {total_trades} total, {open_trades} open')

    # Last trade date
    cur.execute('SELECT MAX(entry_date) FROM algo_trades WHERE status IN (\'open\', \'closed\')')
    row = cur.fetchone()
    last_date = row[0] if (isinstance(row, (tuple, list)) and row[0]) else None
    print(f'Last trade date: {last_date}')
