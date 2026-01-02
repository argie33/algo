#!/bin/bash
# Direct ECS Task Runner - Bypass CloudFormation deployment issues
# Runs loaders directly using existing task definitions

set -e

CLUSTER="stocks-cluster"
REGION="us-east-1"

# Get network configuration from stocks-app-stack
SUBNETS=$(aws cloudformation describe-stacks --stack-name stocks-app-stack --query 'Stacks[0].Outputs[?OutputKey==`PublicSubnet1Id` || OutputKey==`PublicSubnet2Id`].OutputValue' --output text 2>/dev/null || \
         aws ec2 describe-subnets --filters "Name=tag:Name,Values=*Public*" --query 'Subnets[0:2].SubnetId' --output text)
SECURITY_GROUP=$(aws cloudformation describe-stacks --stack-name stocks-app-stack --query 'Stacks[0].Outputs[?OutputKey==`EcsTasksSecurityGroupId`].OutputValue' --output text 2>/dev/null || \
                aws ec2 describe-security-groups --filters "Name=tag:Name,Values=*ECS*" --query 'SecurityGroups[0].GroupId' --output text)

SUBNET1=$(echo $SUBNETS | awk '{print $1}')
SUBNET2=$(echo $SUBNETS | awk '{print $2}')

echo "=========================================="
echo "Running Data Loaders Directly in ECS"
echo "=========================================="
echo "Cluster: $CLUSTER"
echo "Subnets: $SUBNET1, $SUBNET2"
echo "Security Group: $SECURITY_GROUP"
echo ""

# Define loaders to run with their task definition families
declare -A LOADERS=(
    ["stocksymbols"]="stocksymbols-loader"
    ["pricedaily"]="pricedaily-loader"
    ["buyselldaily"]="buyselldaily-loader"
    ["stockscores"]="stock-scores"
    ["loaddailycompanydata"]="loaddailycompanydata-loader"
)

# Run each loader
for loader_name in "${!LOADERS[@]}"; do
    task_family="${LOADERS[$loader_name]}"

    echo "----------------------------------------"
    echo "🚀 Running: $loader_name ($task_family)"
    echo "----------------------------------------"

    # Run task
    TASK_ARN=$(aws ecs run-task \
        --cluster $CLUSTER \
        --task-definition $task_family \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET1,$SUBNET2],securityGroups=[$SECURITY_GROUP],assignPublicIp=ENABLED}" \
        --region $REGION \
        --query 'tasks[0].taskArn' \
        --output text 2>&1)

    if [[ "$TASK_ARN" == arn:* ]]; then
        echo "✅ Task started: $TASK_ARN"
        TASK_ID=$(echo $TASK_ARN | awk -F'/' '{print $NF}')
        echo "   Task ID: $TASK_ID"
        echo "   Logs: https://console.aws.amazon.com/ecs/v2/clusters/$CLUSTER/tasks/$TASK_ID"
    else
        echo "❌ Failed to start task"
        echo "   Error: $TASK_ARN"
    fi
    echo ""
done

echo "=========================================="
echo "All loaders started!"
echo ""
echo "Monitor tasks at:"
echo "https://console.aws.amazon.com/ecs/v2/clusters/$CLUSTER/tasks"
echo "=========================================="
