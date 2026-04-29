#!/bin/bash
# Batch 5 Status Checker - Run this to get current execution status

set -e

echo "================================================"
echo "BATCH 5 EXECUTION STATUS CHECKER"
echo "================================================"
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Install with:"
    echo "   curl 'https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip' -o 'awscliv2.zip'"
    echo "   unzip awscliv2.zip"
    echo "   sudo ./aws/install"
    exit 1
fi

# Check if gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI not found. Install with:"
    echo "   brew install gh  # or apt-get install gh"
    exit 1
fi

echo "✓ Required tools found (AWS CLI, GitHub CLI)"
echo ""

# Get GitHub Actions workflow status
echo "================================================"
echo "1. GITHUB ACTIONS WORKFLOW STATUS"
echo "================================================"
gh run list --workflow=deploy-app-stocks.yml --limit=3 --json status,conclusion,createdAt,number,displayTitle -q '.[0] | "\(.number): \(.displayTitle)\nStatus: \(.status) | Conclusion: \(.conclusion)\nStarted: \(.createdAt)"' 2>/dev/null || echo "Could not get GitHub Actions status (may need: gh auth login)"
echo ""

# Get ECS task status
echo "================================================"
echo "2. ECS TASK STATUS"
echo "================================================"
echo "Checking stocks-cluster for running tasks..."

# List running tasks
TASKS=$(aws ecs list-tasks --cluster stocks-cluster --desired-status RUNNING --query 'taskArns[]' --output text 2>/dev/null || echo "")

if [ -z "$TASKS" ]; then
    echo "No running tasks found. Checking stopped tasks..."
    TASKS=$(aws ecs list-tasks --cluster stocks-cluster --desired-status STOPPED --query 'taskArns[]' --output text 2>/dev/null || echo "")
fi

if [ -z "$TASKS" ]; then
    echo "⚠️ No tasks found in cluster"
else
    echo "Found tasks:"
    for TASK in $TASKS; do
        TASK_NAME=$(echo $TASK | rev | cut -d'/' -f1 | rev)
        echo "  - $TASK_NAME"
    done

    # Get detailed status
    echo ""
    echo "Task Details:"
    aws ecs describe-tasks --cluster stocks-cluster --tasks $TASKS --query 'tasks[].[taskArn,lastStatus,desiredStatus,executionStoppedAt,stoppedAt]' --output table 2>/dev/null || echo "Could not get task details"
fi
echo ""

# Get CloudWatch Logs
echo "================================================"
echo "3. CLOUDWATCH LOGS (Last 100 lines)"
echo "================================================"
echo "Fetching logs from /aws/ecs/stocks-loader-tasks..."
echo ""

# List log streams
STREAMS=$(aws logs describe-log-streams --log-group-name /aws/ecs/stocks-loader-tasks --query 'logStreams[].logStreamName' --output text 2>/dev/null || echo "")

if [ -z "$STREAMS" ]; then
    echo "❌ No log streams found (logs may not have been created yet)"
else
    for STREAM in $STREAMS; do
        echo "--- LOG STREAM: $STREAM ---"
        aws logs get-log-events --log-group-name /aws/ecs/stocks-loader-tasks --log-stream-name "$STREAM" --query 'events[-100:].message' --output text 2>/dev/null | tail -50
        echo ""
    done
fi

# Get error summary
echo "================================================"
echo "4. ERROR SUMMARY"
echo "================================================"
echo "Searching for ERROR messages in logs..."
aws logs filter-log-events --log-group-name /aws/ecs/stocks-loader-tasks --filter-pattern "ERROR" --query 'events[].message' --output text 2>/dev/null | head -20 || echo "No errors found or logs not accessible"
echo ""

# Database status
echo "================================================"
echo "5. DATABASE RECORD COUNT (if accessible)"
echo "================================================"
if command -v psql &> /dev/null; then
    echo "Checking database table row counts..."
    psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
         -U stocks -d stocks -c "
        SELECT 'annual_cash_flow' as table_name, COUNT(*) as rows FROM annual_cash_flow
        UNION
        SELECT 'quarterly_cash_flow', COUNT(*) FROM quarterly_cash_flow
        UNION
        SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
        UNION
        SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
        UNION
        SELECT 'stock_scores', COUNT(*) FROM stock_scores;" 2>/dev/null || echo "Could not connect to database"
else
    echo "psql not available - cannot check database"
fi
echo ""

echo "================================================"
echo "STATUS CHECK COMPLETE"
echo "================================================"
