#!/bin/bash
# Manually trigger a specific loader in ECS for testing

set -e
AWS_REGION="us-east-1"

LOADER_NAME="${1:-stock_prices_daily}"
if [ -z "$LOADER_NAME" ]; then
    echo "Usage: trigger-loader-ecs.sh <loader_name> [options]"
    echo ""
    echo "Examples:"
    echo "  trigger-loader-ecs.sh stock_prices_daily"
    echo "  trigger-loader-ecs.sh stock_symbols"
    echo "  trigger-loader-ecs.sh signals_daily"
    exit 1
fi

echo "🚀 Triggering ECS Loader: $LOADER_NAME"
echo "======================================"

# ============================================================
# Get cluster and task definition
# ============================================================
echo ""
echo "1️⃣  Finding ECS cluster and task definition..."
CLUSTER=$(aws ecs list-clusters --region $AWS_REGION --query 'clusterArns[0]' --output text 2>/dev/null || echo "")
if [ -z "$CLUSTER" ] || [ "$CLUSTER" == "None" ]; then
    echo "❌ No ECS cluster found"
    exit 1
fi
CLUSTER_NAME=$(echo $CLUSTER | cut -d/ -f2)
echo "✅ Cluster: $CLUSTER_NAME"

# Find task definition
TASK_DEF=$(aws ecs list-task-definitions \
    --family-prefix "algo-${LOADER_NAME}-loader" \
    --region $AWS_REGION \
    --query 'taskDefinitionArns[0]' \
    --output text 2>/dev/null || echo "")

if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" == "None" ]; then
    echo "❌ Task definition not found for $LOADER_NAME"
    echo ""
    echo "Available task definitions:"
    aws ecs list-task-definitions --region $AWS_REGION --query 'taskDefinitionArns' --output text 2>/dev/null | tr '\t' '\n' | grep "loader" | head -10
    exit 1
fi

TASK_NAME=$(echo $TASK_DEF | rev | cut -d: -f1 | rev)
echo "✅ Task Definition: $TASK_NAME"

# ============================================================
# Get VPC configuration from existing task
# ============================================================
echo ""
echo "2️⃣  Getting VPC configuration..."
VPC_CONFIG=$(aws ecs describe-task-definition \
    --task-definition "$TASK_DEF" \
    --region $AWS_REGION \
    --query 'taskDefinition.networkMode' \
    --output text)
echo "✅ Network Mode: $VPC_CONFIG"

# Get subnets and security groups from task definition
SUBNET=$(aws ecs describe-task-definition \
    --task-definition "$TASK_DEF" \
    --region $AWS_REGION \
    --query 'taskDefinition' \
    --output json | jq -r '.networkMode')

echo "Getting VPC details from ECS cluster..."
# Try to get existing task's network config
EXISTING_TASK=$(aws ecs list-tasks --cluster $CLUSTER_NAME --region $AWS_REGION --query 'taskArns[0]' --output text 2>/dev/null || echo "")
if [ -n "$EXISTING_TASK" ] && [ "$EXISTING_TASK" != "None" ]; then
    TASK_DETAILS=$(aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $EXISTING_TASK --region $AWS_REGION --query 'tasks[0]' --output json)
    SUBNET=$(echo $TASK_DETAILS | jq -r '.attachments[0].details[] | select(.name=="subnet") | .value' | head -1)
    SG=$(echo $TASK_DETAILS | jq -r '.attachments[0].details[] | select(.name=="securityGroup") | .value' | head -1)
    echo "✅ Subnet: $SUBNET"
    echo "✅ Security Group: $SG"
fi

# ============================================================
# Run task
# ============================================================
echo ""
echo "3️⃣  Running task..."
TASK_RUN=$(aws ecs run-task \
    --cluster $CLUSTER_NAME \
    --task-definition "$TASK_DEF" \
    --launch-type FARGATE \
    --network-configuration awsvpcConfiguration="{subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
    --region $AWS_REGION \
    --query 'tasks[0].taskArn' \
    --output text 2>&1)

if echo "$TASK_RUN" | grep -q "error\|Error\|ERROR"; then
    echo "❌ Failed to run task:"
    echo "$TASK_RUN"
    exit 1
fi

TASK_ID=$(echo $TASK_RUN | rev | cut -d/ -f1 | rev)
echo "✅ Task Started: $TASK_ID"

# ============================================================
# Monitor task
# ============================================================
echo ""
echo "4️⃣  Monitoring task execution..."
echo "   (Check logs every 5 seconds...)"
echo ""

for i in {1..60}; do
    STATUS=$(aws ecs describe-tasks \
        --cluster $CLUSTER_NAME \
        --tasks $TASK_RUN \
        --region $AWS_REGION \
        --query 'tasks[0].lastStatus' \
        --output text 2>/dev/null || echo "UNKNOWN")

    if [ "$STATUS" != "RUNNING" ] && [ "$STATUS" != "PROVISIONING" ]; then
        echo "Task Status: $STATUS"
        break
    fi

    sleep 5
done

# ============================================================
# Display logs
# ============================================================
echo ""
echo "5️⃣  Fetching logs..."
LOG_GROUP="/ecs/algo-${LOADER_NAME}-loader"
echo "Log Group: $LOG_GROUP"
echo ""

# Get the log stream for this task
LOG_STREAM=$(aws logs describe-log-streams \
    --log-group-name "$LOG_GROUP" \
    --region $AWS_REGION \
    --order-by LastEventTime \
    --descending \
    --max-items 1 \
    --query 'logStreams[0].logStreamName' \
    --output text 2>/dev/null || echo "")

if [ -n "$LOG_STREAM" ] && [ "$LOG_STREAM" != "None" ]; then
    echo "Log Stream: $LOG_STREAM"
    echo ""
    aws logs get-log-events \
        --log-group-name "$LOG_GROUP" \
        --log-stream-name "$LOG_STREAM" \
        --region $AWS_REGION \
        --query 'events[].message' \
        --output text 2>/dev/null || echo "No logs yet"
else
    echo "No logs found yet. Try again in a moment."
fi

echo ""
echo "📋 To see live logs:"
echo "   aws logs tail '$LOG_GROUP' --follow --region $AWS_REGION"
echo ""
echo "✨ Task execution started! Check CloudWatch for detailed logs."
