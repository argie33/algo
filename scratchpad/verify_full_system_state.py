#!/usr/bin/env python3
import boto3
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

print("=== COMPLETE SYSTEM VERIFICATION ===\n")

db = DatabaseContext('read')
with db as cur:
    # 1. Check if recent orchestrator runs generated signals
    print("1. ORCHESTRATOR SIGNAL GENERATION:")
    cur.execute('''
        SELECT COUNT(*) as count, MAX(generated_at) as latest
        FROM algo_signals
        WHERE generated_at >= CURRENT_DATE - INTERVAL '1 day'
    ''')
    row = cur.fetchone()
    print(f"   Signals generated today: {row['count']}")
    print(f"   Latest: {row['latest']}")

    # 2. Check if orchestrator is generating buy signals
    print("\n2. BUY SIGNALS:")
    cur.execute('''
        SELECT COUNT(*) as buy_count FROM algo_signals
        WHERE signal_type = 'BUY' AND generated_at >= CURRENT_DATE - INTERVAL '1 day'
    ''')
    row = cur.fetchone()
    print(f"   Buy signals today: {row['buy_count']}")

    # 3. Check if new trades were created after pipeline started
    print("\n3. TRADE GENERATION (After Pipeline Start - 2026-07-06 11:18):")
    cur.execute('''
        SELECT COUNT(*) as count, MAX(entry_date) as latest
        FROM algo_trades
        WHERE entry_date >= '2026-07-06'
    ''')
    row = cur.fetchone()
    print(f"   Trades since pipeline start: {row['count']}")
    print(f"   Latest trade: {row['latest']}")

    # 4. Check if positions have been updated with latest metrics
    print("\n4. POSITION QUALITY SCORES:")
    cur.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN signal_quality_score >= 60 THEN 1 ELSE 0 END) as qualified
        FROM algo_positions
        WHERE status = 'open'
    ''')
    row = cur.fetchone()
    print(f"   Open positions: {row['total']}")
    print(f"   With quality score >=60: {row['qualified']}")

    # 5. Data completeness for trading
    print("\n5. DATA COMPLETENESS FOR SIGNALS:")
    cur.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN data_unavailable = FALSE THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN growth_score IS NOT NULL AND quality_score IS NOT NULL THEN 1 ELSE 0 END) as full_metrics
        FROM stock_scores
    ''')
    row = cur.fetchone()
    available_pct = (row['available'] / row['total'] * 100) if row['total'] > 0 else 0
    metrics_pct = (row['full_metrics'] / row['total'] * 100) if row['total'] > 0 else 0
    print(f"   Total stocks: {row['total']}")
    print(f"   Data available: {row['available']} ({available_pct:.1f}%)")
    print(f"   With growth+quality scores: {row['full_metrics']} ({metrics_pct:.1f}%)")

    # 6. Check for any circuit breaker triggers
    print("\n6. CIRCUIT BREAKER STATUS:")
    cur.execute('''
        SELECT any_triggered, COUNT(*) as count
        FROM circuit_breaker_status
        WHERE check_date >= CURRENT_DATE - INTERVAL '2 days'
        GROUP BY any_triggered
    ''')
    rows = cur.fetchall()
    for row in rows:
        status = "TRIGGERED" if row['any_triggered'] else "OK"
        print(f"   {status}: {row['count']} checks")

    # 7. Latest orchestrator status
    print("\n7. ORCHESTRATOR STATUS:")
    cur.execute('''
        SELECT run_id, overall_status, phases_completed, phases_errored, started_at
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 5
    ''')
    rows = cur.fetchall()
    for row in rows:
        status_icon = "✅" if row['overall_status'] == 'success' else "❌"
        print(f"   {status_icon} {row['run_id']}: {row['overall_status']} (phases {row['phases_completed']}/{row['phases_errored']})")
