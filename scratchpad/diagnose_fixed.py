#!/usr/bin/env python3
from utils.db.context import DatabaseContext

db = DatabaseContext('read')
with db as cur:
    # 1. Check recent orchestrator errors
    print('=== ORCHESTRATOR FAILURES TODAY ===')
    cur.execute('''
        SELECT run_id, overall_status, halt_reason, started_at
        FROM orchestrator_execution_log
        WHERE overall_status = 'error' AND started_at >= CURRENT_DATE
        ORDER BY started_at DESC
        LIMIT 3
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["run_id"]}: {row["overall_status"]}')
        if row['halt_reason']:
            print(f'  Halt reason: {row["halt_reason"][:200]}')

    # 2. Check circuit breaker schema
    print('\n=== CIRCUIT_BREAKER_STATUS SCHEMA ===')
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'circuit_breaker_status'
        ORDER BY ordinal_position
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'  {row["column_name"]}: {row["data_type"]}')

    # 3. Check if there are any open positions
    print('\n=== POSITIONS COUNT ===')
    cur.execute('''
        SELECT status, COUNT(*) as count
        FROM algo_positions
        GROUP BY status
        ORDER BY status
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["status"]}: {row["count"]}')

    # 4. Check portfolio_snapshots (what Phase 9 needs)
    print('\n=== PORTFOLIO SNAPSHOTS (Last 5) ===')
    cur.execute('''
        SELECT snapshot_date, total_value, cash_available, trades_count, positions_count
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["snapshot_date"]}: value={row["total_value"]}, cash={row["cash_available"]}')

    # 5. Check data completeness
    print('\n=== STOCK_SCORES DATA AVAILABILITY ===')
    cur.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN data_unavailable = FALSE THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END) as has_quality,
            SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as has_growth
        FROM stock_scores
    ''')
    row = cur.fetchone()
    pct_available = (row['available'] / row['total'] * 100) if row['total'] > 0 else 0
    pct_quality = (row['has_quality'] / row['total'] * 100) if row['total'] > 0 else 0
    pct_growth = (row['has_growth'] / row['total'] * 100) if row['total'] > 0 else 0

    print(f'Total stocks: {row["total"]}')
    print(f'  Available (not marked unavailable): {row["available"]} ({pct_available:.1f}%)')
    print(f'  With quality_score: {row["has_quality"]} ({pct_quality:.1f}%)')
    print(f'  With growth_score: {row["has_growth"]} ({pct_growth:.1f}%)')
