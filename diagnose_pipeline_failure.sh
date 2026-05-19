#!/bin/bash
# Diagnostic script to identify WHY the EOD pipeline failed
# Run this in your AWS environment with proper credentials
#
# Usage:
#   ./diagnose_pipeline_failure.sh

set -e

echo "========================================="
echo "EOD PIPELINE FAILURE DIAGNOSIS"
echo "========================================="
echo ""

EXECUTION_ARN="${EXECUTION_ARN:-arn:aws:states:us-east-1:626216981288:execution:algo-eod-pipeline-dev:auto-populate-1779152959}"
REGION="${AWS_REGION:-us-east-1}"

echo "📋 Checking Step Functions execution..."
echo "Execution ARN: $EXECUTION_ARN"
echo ""

# Get execution status
STATUS=$(aws stepfunctions describe-execution \
  --execution-arn "$EXECUTION_ARN" \
  --region "$REGION" \
  --query 'status' \
  --output text 2>/dev/null || echo "ERROR")

echo "Status: $STATUS"
echo ""

if [ "$STATUS" = "FAILED" ]; then
  echo "❌ Pipeline FAILED. Extracting failure details..."
  echo ""

  # Get failure cause
  CAUSE=$(aws stepfunctions describe-execution \
    --execution-arn "$EXECUTION_ARN" \
    --region "$REGION" \
    --query 'cause' \
    --output text)

  echo "Failure Cause:"
  echo "$CAUSE"
  echo ""
fi

# Get execution history to find which step failed
echo "📝 Execution History (last 50 events):"
echo "========================================="

aws stepfunctions get-execution-history \
  --execution-arn "$EXECUTION_ARN" \
  --region "$REGION" \
  --max-items 100 \
  --query 'events[?type==`TaskFailed` || type==`ExecutionFailed` || type==`StepFailed`].{type: type, state: stateEnteredEventDetails.name, error: executionFailedEventDetails.error}' \
  --output table

echo ""
echo "========================================="
echo ""

# Check CloudWatch logs for the failing loader
echo "🔍 Checking CloudWatch logs..."
echo ""

# Get the most recent failed loader from ECS logs
aws logs tail /ecs/algo-eod-pipeline-dev --since 30m --max-items 100 2>/dev/null | \
  grep -E "ERROR|FAIL|Exception|Traceback" | \
  head -20 || echo "No error logs found in recent 30 minutes"

echo ""
echo "========================================="
echo ""

# Check if it's a database connection issue
echo "🗄️  Checking database connectivity..."

DB_HOST=$(aws secretsmanager get-secret-value \
  --secret-id algo/db/postgres \
  --region "$REGION" \
  --query 'SecretString' \
  --output text 2>/dev/null | \
  jq -r '.host // "unknown"' || echo "unknown")

DB_USER=$(aws secretsmanager get-secret-value \
  --secret-id algo/db/postgres \
  --region "$REGION" \
  --query 'SecretString' \
  --output text 2>/dev/null | \
  jq -r '.username // "stocks"' || echo "stocks")

echo "Database: $DB_HOST"
echo "User: $DB_USER"
echo ""

# Check if database tables exist
if command -v psql &> /dev/null; then
  echo "Testing database connection..."
  psql -h "$DB_HOST" -U "$DB_USER" -d stocks \
    -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name LIMIT 10;" \
    2>&1 | head -20 || echo "Cannot connect to database"
else
  echo "psql not available - skipping database check"
fi

echo ""
echo "========================================="
echo ""

# Check Fargate task definition
echo "⚙️  Checking Fargate task definition..."

TASK_DEFS=$(aws ecs list-task-definitions \
  --family-prefix algo-eod-pipeline \
  --region "$REGION" \
  --query 'taskDefinitionArns[-1]' \
  --output text 2>/dev/null || echo "none")

if [ "$TASK_DEFS" != "none" ]; then
  MEMORY=$(aws ecs describe-task-definition \
    --task-definition "$TASK_DEFS" \
    --region "$REGION" \
    --query 'taskDefinition.memory' \
    --output text 2>/dev/null || echo "unknown")

  CPU=$(aws ecs describe-task-definition \
    --task-definition "$TASK_DEFS" \
    --region "$REGION" \
    --query 'taskDefinition.cpu' \
    --output text 2>/dev/null || echo "unknown")

  echo "Task Definition: $TASK_DEFS"
  echo "Memory: $MEMORY MB"
  echo "CPU: $CPU"
else
  echo "No task definitions found"
fi

echo ""
echo "========================================="
echo "✅ Diagnostic complete!"
echo ""
echo "Next steps:"
echo "1. Check the failure cause above"
echo "2. Compare with TROUBLESHOOT_DATA_LOADING.md for solutions"
echo "3. Apply the fix to the code"
echo "4. Commit and push to trigger re-deployment"
echo ""
