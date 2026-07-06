#!/usr/bin/env python3
import boto3
from utils.db.context import DatabaseContext
from datetime import datetime

print("=== SYSTEM STATUS VERIFICATION ===\n")

# 1. Check metrics pipeline status
sfn = boto3.client('stepfunctions', region_name='us-east-1')
response = sfn.list_state_machines(maxResults=20)

print("1. COMPUTED METRICS PIPELINE STATUS:")
for sm in response['stateMachines']:
    if 'computed-metrics' in sm['name']:
        exec_response = sfn.list_executions(
            stateMachineArn=sm['stateMachineArn'],
            maxResults=1
        )
        if exec_response['executions']:
            exec = exec_response['executions'][0]
            print(f"   Latest execution: {exec['name']}")
            print(f"   Status: {exec['status']}")
            print(f"   Started: {exec['startDate']}")
            print(f"   Duration so far: {(datetime.utcnow() - exec['startDate'].replace(tzinfo=None)).total_seconds() / 60:.1f} minutes")
        break

# 2. Check growth scores progress
db = DatabaseContext('read')
with db as cur:
    print("\n2. GROWTH SCORES IN DATABASE:")
    cur.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_score,
            MAX(updated_at) as latest_update
        FROM stock_scores
    ''')
    row = cur.fetchone()
    pct = (row['with_score'] / row['total'] * 100) if row['total'] > 0 else 0
    print(f"   Total stocks: {row['total']}")
    print(f"   With growth_score: {row['with_score']} ({pct:.1f}%)")
    print(f"   Latest update: {row['latest_update']}")

    # 3. Check orchestrator status
    print("\n3. ORCHESTRATOR STATUS:")
    cur.execute('''
        SELECT run_id, overall_status, started_at
        FROM orchestrator_execution_log
        ORDER BY started_at DESC
        LIMIT 3
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f"   {row['run_id']}: {row['overall_status']} ({row['started_at']})")

    # 4. Check open positions
    print("\n4. OPEN POSITIONS:")
    cur.execute('''
        SELECT COUNT(*) as count
        FROM algo_positions
        WHERE status = 'open'
    ''')
    row = cur.fetchone()
    print(f"   Open positions: {row['count']}")

    # 5. Check recent trades
    print("\n5. RECENT TRADES:")
    cur.execute('''
        SELECT COUNT(*) as count, MAX(entry_date) as latest
        FROM algo_trades
        WHERE entry_date >= '2026-07-04'
    ''')
    row = cur.fetchone()
    print(f"   Trades since Jul 4: {row['count']}")
    print(f"   Latest trade: {row['latest']}")
