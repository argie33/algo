#!/bin/bash
# ONE COMMAND TO RESOLVE: Check if data is in AWS, if not trigger pipeline immediately

set -e

echo "=========================================="
echo "CHECKING AWS FACTOR INPUTS STATUS"
echo "=========================================="
echo ""

# Step 1: Check if data already exists in AWS RDS
echo "Checking AWS RDS for existing data..."
python3 << 'CHECK_DATA' 2>/dev/null || true
import psycopg2
try:
    c = psycopg2.connect(
        host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
        port=5432, database="algo_prod",
        user="algo_admin", password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe",
        sslmode="require", connect_timeout=3
    )
    cur = c.cursor()
    cur.execute("SELECT COUNT(*), COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) FROM stock_scores")
    total, quality = cur.fetchone()
    if total > 1000:
        print(f"[OK] FACTOR INPUTS FOUND IN AWS!")
        print(f"     {total:,} stocks in AWS RDS")
        print(f"     {quality:,} with quality_score populated")
        print(f"     DATA IS VISIBLE - you can now use /api/scores endpoint")
        c.close()
        exit(0)
    c.close()
except:
    pass

# Step 2: If not found, check pipeline status
echo ""
echo "Data not found in AWS RDS. Checking pipeline status..."
echo ""

ARN=$(aws stepfunctions list-state-machines --region us-east-1 \
  --query "stateMachines[?contains(name,'computed-metrics-pipeline')].stateMachineArn" \
  --output text 2>/dev/null || echo "")

if [ -z "$ARN" ]; then
  echo "[ERROR] Pipeline state machine not found - cannot proceed"
  exit 1
fi

# Check if pipeline is already running
STATUS=$(aws stepfunctions list-executions --state-machine-arn "$ARN" \
  --max-items 1 --region us-east-1 \
  --query "executions[0].status" --output text 2>/dev/null || echo "")

if [ "$STATUS" = "RUNNING" ]; then
  echo "[OK] Pipeline is CURRENTLY EXECUTING"
  echo "     Data will appear in AWS RDS when it completes (3-8 hours)"
  exit 0
elif [ "$STATUS" = "SUCCEEDED" ]; then
  echo "[OK] Pipeline completed successfully"
  echo "     If data not in RDS, may need to wait for replication"
  exit 0
fi

# Step 3: If not running, trigger it NOW
echo "Pipeline not running. TRIGGERING IT NOW..."
echo ""

EXEC=$(aws stepfunctions start-execution \
  --state-machine-arn "$ARN" \
  --name "manual-$(date +%s)" \
  --region us-east-1 \
  --query "executionArn" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXEC" ]; then
  echo "[OK] PIPELINE TRIGGERED!"
  echo "     Execution: $EXEC"
  echo ""
  echo "Factor input data will load in 3-8 hours."
  echo "Then you can access it via:"
  echo "  - AWS RDS query"
  echo "  - API endpoint: /api/scores"
  echo "  - Dashboard"
else
  echo "[ERROR] Failed to trigger pipeline"
  exit 1
fi
