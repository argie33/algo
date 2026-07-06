#!/usr/bin/env python3
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

db = DatabaseContext('read')
with db as cur:
    # 1. Check recent orchestrator errors
    print('=== RECENT ORCHESTRATOR RUNS WITH ERRORS ===')
    cur.execute('''
        SELECT run_id, overall_status, phases_completed, phases_errored, halt_reason, started_at
        FROM orchestrator_execution_log
        WHERE overall_status IN ('error', 'failed')
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["run_id"]}: {row["overall_status"]} ({row["phases_completed"]} complete, {row["phases_errored"]} errored)')
        if row['halt_reason']:
            print(f'  Reason: {row["halt_reason"][:150]}')

    # 2. Check circuit breaker status
    print('\n=== CIRCUIT BREAKER STATUS ===')
    cur.execute('''
        SELECT COUNT(*) as count FROM circuit_breaker_status
        WHERE is_breaker_open = TRUE
    ''')
    row = cur.fetchone()
    print(f'Open breakers: {row["count"]}')

    # 3. Check if there are any open positions
    print('\n=== POSITIONS STATUS ===')
    cur.execute('''
        SELECT COUNT(*) as open_count,
               (SELECT COUNT(*) FROM algo_positions WHERE status = 'closed') as closed_count
        FROM algo_positions
        WHERE status = 'open'
    ''')
    row = cur.fetchone()
    print(f'Open: {row["open_count"]}, Closed: {row["closed_count"]}')

    # 4. Check signal generation status
    print('\n=== SIGNAL GENERATION STATUS ===')
    cur.execute('''
        SELECT COUNT(*) as count FROM daily_signals
        WHERE signal_date >= CURRENT_DATE - INTERVAL '7 days'
    ''')
    row = cur.fetchone()
    print(f'Signals generated in past 7 days: {row["count"]}')

    # 5. Check algo_signals table
    print('\n=== ALGO_SIGNALS TABLE ===')
    cur.execute('''
        SELECT COUNT(*) as count FROM algo_signals
        WHERE generated_at >= CURRENT_DATE - INTERVAL '7 days'
    ''')
    row = cur.fetchone()
    print(f'Signals in algo_signals (past 7 days): {row["count"]}')

    # 6. Check trades since Jun 16
    print('\n=== TRADES SINCE JUN 16 ===')
    cur.execute('''
        SELECT COUNT(*) as count, MAX(entry_date) as latest
        FROM algo_trades
        WHERE entry_date >= '2026-06-16'
    ''')
    row = cur.fetchone()
    print(f'Total: {row["count"]}, Latest: {row["latest"]}')

    # 7. Check data completeness
    print('\n=== DATA COMPLETENESS FOR STOCK_SCORES ===')
    cur.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN quality_score IS NOT NULL THEN 1 ELSE 0 END) as with_quality,
            SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_growth,
            SUM(CASE WHEN data_unavailable = FALSE THEN 1 ELSE 0 END) as available
        FROM stock_scores
    ''')
    row = cur.fetchone()
    print(f'Total stocks: {row["total"]}')
    print(f'  With quality_score: {row["with_quality"]}')
    print(f'  With growth_score: {row["with_growth"]}')
    print(f'  Data available: {row["available"]}')
