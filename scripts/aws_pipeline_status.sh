#!/bin/bash
# Comprehensive AWS pipeline status diagnostic
# Run in CloudShell to see why factor inputs aren't visible in AWS

echo "=========================================="
echo "AWS FACTOR INPUTS PIPELINE STATUS"
echo "=========================================="
echo ""

python3 << 'PYTHON_EOF'
import boto3
import psycopg2
from datetime import datetime, timedelta

print("1. CHECKING STEP FUNCTIONS EXECUTION HISTORY...")
print("-" * 60)

sfn = boto3.client('stepfunctions', region_name='us-east-1')

# Find the computed_metrics_pipeline state machine
response = sfn.list_state_machines()
pipeline_arn = None
for sm in response['stateMachines']:
    if 'computed-metrics-pipeline' in sm['name']:
        pipeline_arn = sm['stateMachineArn']
        print(f"[OK] Found: {sm['name']}")
        break

if not pipeline_arn:
    print("[FAIL] computed-metrics-pipeline state machine not found!")
    print("       Terraform may not have deployed it")
else:
    # Get execution history
    executions = sfn.list_executions(
        stateMachineArn=pipeline_arn,
        statusFilter='ALL',
        maxItems=5
    )

    if not executions['executions']:
        print("[FAIL] Pipeline has NEVER run")
        print("       Scheduled trigger at 7:00 PM ET hasn't fired yet")
    else:
        print(f"\nRecent executions:")
        for ex in executions['executions']:
            status = ex['status']
            started = ex.get('startDate', 'N/A')
            symbol = "✓" if status == "SUCCEEDED" else "✗" if status == "FAILED" else "→"
            print(f"  {symbol} {status:<12} | {started}")

        # Check most recent execution
        latest = executions['executions'][0]
        if latest['status'] == 'FAILED':
            details = sfn.describe_execution(executionArn=latest['executionArn'])
            print(f"\n[FAIL] Latest execution FAILED")
            if 'cause' in details:
                print(f"Cause: {details['cause'][:200]}")
        elif latest['status'] == 'RUNNING':
            print(f"\n[RUNNING] Pipeline currently executing")
        else:
            print(f"\n[OK] Latest execution succeeded")

print("\n2. CHECKING AWS RDS DATA...")
print("-" * 60)

try:
    conn = psycopg2.connect(
        host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
        port=5432,
        database="algo_prod",
        user="algo_admin",
        password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe",
        sslmode="require"
    )
    cur = conn.cursor()

    # Check metric table row counts
    tables = ['quality_metrics', 'growth_metrics', 'value_metrics', 'positioning_metrics', 'stability_metrics', 'stock_scores']

    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        status = "[OK]" if count > 1000 else "[EMPTY]"
        print(f"{status} {table:<25} {count:>6,} rows")

    cur.close()
    conn.close()

except Exception as e:
    print(f"[ERROR] Cannot connect to AWS RDS: {e}")
    print("        Check security groups allow CloudShell access")

print("\n" + "=" * 60)
print("DIAGNOSIS:")
print("=" * 60)
print()
print("If you see:")
print("  • [FAIL] Pipeline has NEVER run")
print("    → Scheduler trigger isn't firing (disabled or misconfigured)")
print("    → Action: Check AWS Scheduler console if pipeline is enabled")
print()
print("  • [FAIL] Latest execution FAILED")
print("    → Metric loaders are timing out or crashing in AWS")
print("    → Action: Check CloudWatch logs for /ecs/*-metrics-loader")
print()
print("  • [EMPTY] in AWS RDS")
print("    → Loaders aren't writing to AWS (may be writing to local DB)")
print("    → Action: Verify DB_HOST env var points to AWS RDS endpoint")
print()
print("  • [OK] with data in RDS")
print("    → Data IS there! Check that API/dashboard uses correct endpoint")
print()

PYTHON_EOF

echo ""
echo "=========================================="
echo "Diagnostic complete"
echo "=========================================="
