#!/bin/bash
# Execute full completion cycle: check status, queue missing, monitor

echo "=== FULL COMPLETION CYCLE ==="
echo ""

# Get status
echo "1. Checking current status..."
python3 scripts/full_status_report.py

echo ""
echo "2. Queueing missing loaders..."
python3 scripts/auto_queue_and_verify.py

echo ""
echo "3. Waiting for execution to complete..."
python3 << 'EOF'
import boto3
import time

ecs = boto3.client('ecs', region_name='us-east-1')

for i in range(60):
    all_tasks = []
    paginator = ecs.get_paginator('list_tasks')
    for page in paginator.paginate(cluster='algo-cluster'):
        all_tasks.extend(page['taskArns'])

    count = len(all_tasks)
    print(f"  [{i+1}] {count} tasks running")

    if count == 0:
        print("  COMPLETE: All tasks finished!")
        break

    time.sleep(30)
EOF

echo ""
echo "4. Verifying final data..."
python3 scripts/full_status_report.py
