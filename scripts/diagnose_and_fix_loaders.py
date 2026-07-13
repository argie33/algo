#!/usr/bin/env python3
"""
Diagnose and fix loader failures quickly.

Session 101: Morning pipeline failed on stock_prices_daily ECS task.
This script checks what went wrong and attempts fixes.
"""

import boto3
import sys
from datetime import date

print("=" * 80)
print("LOADER DIAGNOSTIC & RECOVERY TOOL")
print("=" * 80)

# 1. Check data freshness
print("\n[1/5] Checking data freshness...")
import psycopg2

try:
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()
    today = date.today()

    tables_check = {
        'price_daily': f"SELECT COUNT(*) FROM price_daily WHERE date = '{today}'",
        'technical_data_daily': f"SELECT COUNT(*) FROM technical_data_daily WHERE date = '{today}'",
        'buy_sell_daily': f"SELECT COUNT(*) FROM buy_sell_daily WHERE date = '{today}'",
    }

    stale_count = 0
    for table, query in tables_check.items():
        cur.execute(query)
        count = cur.fetchone()[0]
        status = "OK" if count > 100 else "STALE"
        print(f"  {table:<30} {count:>6,} rows [{status}]")
        if count < 100:
            stale_count += 1

    if stale_count == 0:
        print("\n✓ Data is FRESH - loaders have run successfully")
        sys.exit(0)
    else:
        print(f"\n✗ {stale_count} table(s) are STALE - recovery in progress")

    cur.close()
    conn.close()
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# 2. Check pipeline execution status
print("\n[2/5] Checking recent pipeline executions...")
sfn = boto3.client('stepfunctions', region_name='us-east-1')

# Check morning pipeline status
morning_arn = 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev'
eod_arn = 'arn:aws:states:us-east-1:626216981288:stateMachine:algo-eod-pipeline-dev'

for name, arn in [('Morning Pipeline', morning_arn), ('EOD Pipeline', eod_arn)]:
    executions = sfn.list_executions(
        stateMachineArn=arn,
        maxResults=3,
        statusFilter='RUNNING'
    )

    if executions['executions']:
        print(f"  {name}: RUNNING ({len(executions['executions'])} active)")
        for ex in executions['executions']:
            print(f"    - {ex['name']} (started {ex['startDate']})")
    else:
        print(f"  {name}: No active executions")

# 3. Check ECS cluster capacity
print("\n[3/5] Checking ECS cluster resources...")
ecs = boto3.client('ecs', region_name='us-east-1')

try:
    clusters = ecs.list_clusters()
    algo_cluster = next((c for c in clusters['clusterArns'] if 'algo' in c), None)

    if algo_cluster:
        cluster_info = ecs.describe_clusters(clusters=[algo_cluster])
        cluster = cluster_info['clusters'][0]
        print(f"  Cluster: {cluster['clusterName']}")
        print(f"  Status: {cluster['status']}")
        print(f"  Running Tasks: {cluster.get('runningCount', 'N/A')}")
        print(f"  Pending Tasks: {cluster.get('pendingCount', 'N/A')}")
    else:
        print("  No algo cluster found")
except Exception as e:
    print(f"  ERROR: {e}")

# 4. Check EventBridge Scheduler status
print("\n[4/5] Checking EventBridge Scheduler rules...")
scheduler = boto3.client('scheduler', region_name='us-east-1')

try:
    schedules = scheduler.list_schedules(
        GroupName='default',
        NamePrefix='algo-morning-pipeline'
    )

    if schedules['Schedules']:
        for sched in schedules['Schedules']:
            print(f"  Schedule: {sched['Name']}")
            print(f"  State: {sched['State']}")
            print(f"  Next Run: {sched.get('NextExecutionTime', 'Unknown')}")
    else:
        print("  No morning pipeline schedules found")
except Exception as e:
    print(f"  ERROR: {e}")

# 5. Recommended next steps
print("\n[5/5] Recommended actions...")

if stale_count > 0:
    print("""
OPTIONS FOR RECOVERY:

A) Monitor active pipelines (if running):
   $ python3 scripts/monitor_loader_pipeline.py

B) Trigger EOD pipeline manually:
   $ aws stepfunctions start-execution \\
       --state-machine-arn <EOD_PIPELINE_ARN> \\
       --name manual-eod-recovery-$(date +%s)

C) Trigger morning pipeline manually:
   $ aws stepfunctions start-execution \\
       --state-machine-arn <MORNING_PIPELINE_ARN> \\
       --name manual-morning-recovery-$(date +%s)

D) Check why morning pipeline failed:
   - Review CloudWatch Logs: /aws/states/algo-eod-pipeline-dev
   - Check ECS task logs: /ecs/algo-loader
   - Verify Alpaca API credentials in AWS Secrets Manager
   - Check for rate limiting: yfinance may be blocking requests

E) Verify EventBridge Scheduler IAM permissions:
   aws iam get-role-policy \\
     --role-name algo-eventbridge-scheduler-role-dev \\
     --policy-name algo-eventbridge-scheduler-policy

   Should have: "states:StartExecution" on both pipeline ARNs
    """)

print("\n" + "=" * 80)
