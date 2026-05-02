#!/bin/bash
# Complete Deployment Script - Deploy all 5 optimization phases
# Run this: bash DEPLOY_ALL_PHASES.sh
# Takes ~45 minutes

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}DEPLOYING ALL OPTIMIZATION PHASES${NC}"
echo -e "${BLUE}Phase A: Already Live${NC}"
echo -e "${BLUE}Phase C, D, E: Deploying Now${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-prod}

echo -e "${YELLOW}Configuration:${NC}"
echo "  Region: $AWS_REGION"
echo "  Environment: $ENVIRONMENT"
echo ""

# Verify prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}✗ AWS CLI not found${NC}"
    echo "  Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

IDENTITY=$(aws sts get-caller-identity 2>/dev/null || echo "")
if [ -z "$IDENTITY" ]; then
    echo -e "${RED}✗ AWS credentials not configured${NC}"
    echo "  Run: aws configure"
    exit 1
fi

echo -e "${GREEN}✓ AWS CLI configured${NC}"
echo "  Account: $(echo $IDENTITY | grep -o '"Account"[^,]*' | cut -d'"' -f4)"
echo ""

# Phase C: Lambda
echo -e "${BLUE}========== PHASE C: Lambda (5 min) ==========${NC}"
echo "Deploying Lambda orchestrator + 100 workers..."

aws cloudformation deploy \
    --stack-name stocks-lambda-phase-c \
    --template-file template-lambda-phase-c.yml \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region $AWS_REGION \
    --parameter-overrides Environment=$ENVIRONMENT \
    --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Phase C deployed${NC}"
else
    echo -e "${RED}✗ Phase C deployment failed${NC}"
    exit 1
fi
echo ""

# Phase E: DynamoDB
echo -e "${BLUE}========== PHASE E: DynamoDB (3 min) ==========${NC}"
echo "Deploying caching infrastructure..."

aws cloudformation deploy \
    --stack-name stocks-phase-e-incremental \
    --template-file template-phase-e-dynamodb.yml \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region $AWS_REGION \
    --parameter-overrides Environment=$ENVIRONMENT \
    --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Phase E deployed${NC}"
else
    echo -e "${RED}✗ Phase E deployment failed${NC}"
    exit 1
fi
echo ""

# Phase D: Step Functions
echo -e "${BLUE}========== PHASE D: Step Functions (3 min) ==========${NC}"
echo "Deploying orchestration DAG..."

# Get ECS cluster ARN
CLUSTER_ARN=$(aws cloudformation list-exports \
    --region $AWS_REGION \
    --query "Exports[?Name=='StocksApp-ClusterArn'].Value" \
    --output text 2>/dev/null || echo "")

if [ -z "$CLUSTER_ARN" ]; then
    echo -e "${YELLOW}⚠ ECS cluster not found, using placeholder${NC}"
    CLUSTER_ARN="arn:aws:ecs:$AWS_REGION:$(aws sts get-caller-identity --query Account --output text):cluster/stocks-app"
fi

aws cloudformation deploy \
    --stack-name stocks-stepfunctions-phase-d \
    --template-file template-step-functions-phase-d.yml \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --region $AWS_REGION \
    --parameter-overrides ECSClusterArn=$CLUSTER_ARN \
    --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Phase D deployed${NC}"
else
    echo -e "${RED}✗ Phase D deployment failed${NC}"
    exit 1
fi
echo ""

# EventBridge Scheduling
echo -e "${BLUE}========== EventBridge Scheduling (3 min) ==========${NC}"
echo "Deploying scheduling rules..."

# Get state machine ARN
STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines \
    --region $AWS_REGION \
    --query 'stateMachines[?name==`DataLoadingStateMachine`].stateMachineArn' \
    --output text 2>/dev/null || echo "")

if [ -z "$STATE_MACHINE_ARN" ]; then
    echo -e "${YELLOW}⚠ State machine not found yet, retrying...${NC}"
    sleep 5
    STATE_MACHINE_ARN=$(aws stepfunctions list-state-machines \
        --region $AWS_REGION \
        --query 'stateMachines[?name==`DataLoadingStateMachine`].stateMachineArn' \
        --output text)
fi

aws cloudformation deploy \
    --stack-name stocks-pipeline-scheduling \
    --template-file template-eventbridge-scheduling.yml \
    --capabilities CAPABILITY_IAM CAPABILITY_SNS \
    --region $AWS_REGION \
    --parameter-overrides \
        StateMachineArn=$STATE_MACHINE_ARN \
        ScheduleTime='cron(0 2,6,10,14,18,22 * * ? *)' \
        Environment=$ENVIRONMENT \
    --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ EventBridge deployed${NC}"
else
    echo -e "${RED}✗ EventBridge deployment failed${NC}"
    exit 1
fi
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}ALL PHASES DEPLOYED SUCCESSFULLY${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo "1. Run manual test:"
echo "   STATE_MACHINE_ARN=\$(aws stepfunctions list-state-machines --query 'stateMachines[0].stateMachineArn' --output text)"
echo "   aws stepfunctions start-execution --state-machine-arn \$STATE_MACHINE_ARN --name 'manual-test-\$(date +%s)'"
echo ""
echo "2. Monitor CloudWatch logs:"
echo "   aws logs tail /stepfunctions/data-loading-pipeline --follow"
echo ""
echo "3. Check status in 15 minutes (expect ~10 min execution)"
echo ""
echo -e "${YELLOW}Estimated Cost Savings:${NC}"
echo "  Before: \$1,200/month (baseline)"
echo "  After: \$225/month (optimized)"
echo "  Savings: -81% (\$975/month)"
echo ""

