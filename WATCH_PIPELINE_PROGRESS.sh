#!/bin/bash
# Real-time pipeline monitoring
#
# Usage: ./WATCH_PIPELINE_PROGRESS.sh
# This will update every 30 seconds showing current progress

echo "Watching Pipeline Progress - Press Ctrl+C to stop"
echo ""

while true; do
    clear
    echo "=================================="
    echo "PIPELINE PROGRESS MONITOR"
    echo "Updated: $(date)"
    echo "=================================="
    echo ""

    # Get Step Functions execution status
    python3 << 'EOF'
import boto3
from datetime import datetime

sfn = boto3.client('stepfunctions', region_name='us-east-1')

response = sfn.list_executions(
    stateMachineArn='arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev',
    statusFilter='RUNNING',
    maxResults=5
)

if response.get('executions'):
    for exec_info in response['executions']:
        start = exec_info['startDate']
        elapsed_min = (datetime.now(start.tzinfo) - start).total_seconds() / 60
        elapsed_sec = int(((datetime.now(start.tzinfo) - start).total_seconds()) % 60)

        print(f"Status: RUNNING")
        print(f"Elapsed: {int(elapsed_min)}m {elapsed_sec}s")
        print(f"Started: {start}")
else:
    # Check if completed
    for status in ['SUCCEEDED', 'FAILED']:
        resp = sfn.list_executions(
            stateMachineArn='arn:aws:states:us-east-1:626216981288:stateMachine:algo-morning-prep-pipeline-dev',
            statusFilter=status,
            maxResults=1
        )
        if resp.get('executions'):
            exec_info = resp['executions'][0]
            print(f"Status: {status}")
            print(f"Completed: {exec_info['stopDate']}")
            break
EOF

    echo ""
    echo "Data Status:"
    python3 << 'EOF'
import psycopg2

conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
cur = conn.cursor()

queries = [
    ('price_daily', "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE"),
    ('buy_sell_daily', "SELECT COUNT(*) FROM buy_sell_daily WHERE date::date = CURRENT_DATE"),
    ('market_health_daily', "SELECT COUNT(*) FROM market_health_daily WHERE date = CURRENT_DATE"),
]

for table, query in queries:
    try:
        cur.execute(query)
        count = cur.fetchone()[0]
        status = 'FRESH' if count > 0 else 'STALE'
        print(f"  {table:25s}: {count:6d} rows [{status}]")
    except:
        print(f"  {table:25s}: (error reading)")

cur.close()
conn.close()
EOF

    echo ""
    echo "Latest ECS Logs:"
    python3 << 'EOF'
import boto3

logs = boto3.client('logs', region_name='us-east-1')

try:
    response = logs.get_log_events(
        logGroupName='/ecs/algo-stock_prices_daily-loader',
        logStreamName='ecs/algo-stock_prices_daily/e8e88eb4cd464ffcbe5508d5e4358c0c',
        limit=5,
        startFromHead=False
    )

    for event in response['events'][-3:]:
        msg = event['message'].strip()
        if len(msg) > 70:
            msg = msg[:67] + '...'
        print(f"  {msg}")
except Exception as e:
    print(f"  (Could not read logs)")
EOF

    echo ""
    echo "Next check in 30 seconds..."
    sleep 30
done
