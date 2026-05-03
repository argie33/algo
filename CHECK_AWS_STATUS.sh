#!/bin/bash
# Check what's actually running in AWS right now
# Shows: Loaders executing, Lambda functions, Step Functions, Costs

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}AWS EXECUTION STATUS - TODAY${NC}"
echo -e "${BLUE}What's actually running in your AWS${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. Check ECS Loader Executions (Phase A)
echo -e "${YELLOW}1. ECS LOADER EXECUTIONS (Phase A)${NC}"
echo "Checking recently executed ECS tasks..."
ECS_TASKS=$(aws ecs list-tasks --cluster stocks-cluster --desired-status RUNNING 2>/dev/null | jq '.taskArns | length' || echo "0")
echo "Currently running: $ECS_TASKS tasks"

# Check task history
aws ecs list-tasks --cluster stocks-cluster --desired-status STOPPED 2>/dev/null | head -5 || echo "No recent task history"
echo ""

# 2. Check Lambda Executions (Phase C)
echo -e "${YELLOW}2. LAMBDA EXECUTIONS (Phase C)${NC}"
echo "Checking buyselldaily Lambda invocations (last 24h)..."

LAMBDA_INVOCATIONS=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=buyselldaily-orchestrator \
    --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 86400 \
    --statistics Sum \
    2>/dev/null | jq '.Datapoints[0].Sum // 0' || echo "0")

echo "Lambda invocations (24h): $LAMBDA_INVOCATIONS"

if [ "$LAMBDA_INVOCATIONS" -gt "0" ]; then
    echo -e "${GREEN}✓ Lambda is executing${NC}"
else
    echo -e "${YELLOW}⚠ No Lambda executions yet${NC}"
fi
echo ""

# 3. Check Step Functions (Phase D)
echo -e "${YELLOW}3. STEP FUNCTIONS EXECUTIONS (Phase D)${NC}"
echo "Checking Step Functions state machine..."

STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines \
    --query 'stateMachines[0].stateMachineArn' \
    --output text 2>/dev/null || echo "")

if [ ! -z "$STATE_MACHINE_ARN" ] && [ "$STATE_MACHINE_ARN" != "None" ]; then
    EXECUTIONS=$(aws stepfunctions list-executions \
        --state-machine-arn "$STATE_MACHINE_ARN" \
        --max-items 10 \
        --query 'executions | length' \
        2>/dev/null || echo "0")

    echo "Recent executions: $EXECUTIONS"

    # Get latest execution status
    LATEST=$(aws stepfunctions list-executions \
        --state-machine-arn "$STATE_MACHINE_ARN" \
        --sort-order DESCENDING \
        --max-items 1 \
        --query 'executions[0]' \
        2>/dev/null)

    if [ ! -z "$LATEST" ] && [ "$LATEST" != "None" ]; then
        STATUS=$(echo "$LATEST" | jq -r '.status' 2>/dev/null || echo "UNKNOWN")
        START_TIME=$(echo "$LATEST" | jq -r '.startDate' 2>/dev/null || echo "unknown")

        echo "Latest status: $STATUS"
        echo "Started: $START_TIME"

        if [ "$STATUS" = "SUCCEEDED" ]; then
            echo -e "${GREEN}✓ Last execution completed successfully${NC}"
        elif [ "$STATUS" = "RUNNING" ]; then
            echo -e "${YELLOW}⏳ Execution in progress${NC}"
        elif [ "$STATUS" = "FAILED" ]; then
            echo -e "${RED}✗ Last execution failed${NC}"
        fi
    fi
else
    echo -e "${YELLOW}⚠ Step Functions not yet deployed${NC}"
fi
echo ""

# 4. Check Database Data (Latest loads)
echo -e "${YELLOW}4. DATABASE UPDATES (Actual Data)${NC}"
echo "Checking when data was last loaded..."

if command -v psql &> /dev/null; then
    # Check price_daily
    PRICE_DATE=$(psql -h ${DB_HOST:-localhost} -U ${DB_USER:-stocks} -d ${DB_NAME:-stocks} \
        -t -c "SELECT MAX(date) FROM price_daily;" 2>/dev/null || echo "unknown")

    # Check buy_sell_daily
    SIGNAL_DATE=$(psql -h ${DB_HOST:-localhost} -U ${DB_USER:-stocks} -d ${DB_NAME:-stocks} \
        -t -c "SELECT MAX(date) FROM buy_sell_daily;" 2>/dev/null || echo "unknown")

    echo "Price data (latest): $PRICE_DATE"
    echo "Signal data (latest): $SIGNAL_DATE"

    # Check row counts
    PRICE_COUNT=$(psql -h ${DB_HOST:-localhost} -U ${DB_USER:-stocks} -d ${DB_NAME:-stocks} \
        -t -c "SELECT COUNT(*) FROM price_daily;" 2>/dev/null || echo "0")

    SIGNAL_COUNT=$(psql -h ${DB_HOST:-localhost} -U ${DB_USER:-stocks} -d ${DB_NAME:-stocks} \
        -t -c "SELECT COUNT(*) FROM buy_sell_daily;" 2>/dev/null || echo "0")

    echo "Price records: $PRICE_COUNT"
    echo "Signal records: $SIGNAL_COUNT"
else
    echo "psql not available - cannot check database directly"
fi
echo ""

# 5. Check CloudWatch Logs
echo -e "${YELLOW}5. CLOUDWATCH LOGS (Errors/Activity)${NC}"
echo "Checking for recent errors (last 24h)..."

ERROR_COUNT=$(aws logs filter-log-events \
    --log-group-name /stepfunctions/data-loading-pipeline \
    --filter-pattern "ERROR\|FAILED\|Exception" \
    --start-time $(($(date +%s)*1000 - 86400000)) \
    --query 'events | length(@)' \
    --output text 2>/dev/null || echo "0")

echo "Errors found: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt "0" ]; then
    echo -e "${RED}✗ Errors detected${NC}"
    echo "Review: AWS CloudWatch → Log Groups → /stepfunctions/data-loading-pipeline"
else
    echo -e "${GREEN}✓ No recent errors${NC}"
fi
echo ""

# 6. Cost Today
echo -e "${YELLOW}6. COST TODAY${NC}"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d 'yesterday' +%Y-%m-%d)

COST=$(aws ce get-cost-and-usage \
    --time-period Start=$TODAY,End=$TODAY \
    --granularity DAILY \
    --metrics BlendedCost \
    --group-by Type=DIMENSION,Key=SERVICE \
    --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
    --output text 2>/dev/null || echo "0")

echo "Cost today: \$$COST"
echo "Target (optimized): <$5/day"
echo ""

# 7. Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}SUMMARY${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

READY=0
WORKING=0
ISSUES=0

if [ "$LAMBDA_INVOCATIONS" -gt "0" ]; then
    echo -e "${GREEN}✓ Phase C Lambda: Executing${NC}"
    ((WORKING++))
else
    echo -e "${YELLOW}⚠ Phase C Lambda: Not yet deployed${NC}"
    ((READY++))
fi

if [ ! -z "$STATE_MACHINE_ARN" ] && [ "$STATE_MACHINE_ARN" != "None" ]; then
    echo -e "${GREEN}✓ Phase D Step Functions: Deployed${NC}"
    ((WORKING++))
else
    echo -e "${YELLOW}⚠ Phase D Step Functions: Not yet deployed${NC}"
    ((READY++))
fi

if [ "$ERROR_COUNT" -eq "0" ]; then
    echo -e "${GREEN}✓ Error rate: 0${NC}"
else
    echo -e "${RED}✗ Errors detected: $ERROR_COUNT${NC}"
    ((ISSUES++))
fi

echo ""
echo "Status:"
echo "  Working: $WORKING"
echo "  Ready to deploy: $READY"
echo "  Issues: $ISSUES"
echo ""

if [ "$ISSUES" -eq "0" ] && [ "$WORKING" -gt "0" ]; then
    echo -e "${GREEN}SYSTEM OPERATIONAL${NC}"
elif [ "$READY" -gt "0" ]; then
    echo -e "${YELLOW}READY FOR DEPLOYMENT${NC}"
else
    echo -e "${RED}CHECK ISSUES ABOVE${NC}"
fi
echo ""
