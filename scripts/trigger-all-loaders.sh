#!/bin/bash
# ============================================================
# TRIGGER ALL LOADERS IN AWS (Manual execution for testing)
# Runs all 40+ loaders in dependency order via ECS tasks
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_info() { echo -e "${BLUE}ℹ${NC} $1"; }
echo_success() { echo -e "${GREEN}✅${NC} $1"; }
echo_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
echo_error() { echo -e "${RED}❌${NC} $1"; }

AWS_REGION="us-east-1"
PROJECT_NAME="algo"
ENVIRONMENT="dev"
ECS_CLUSTER="${PROJECT_NAME}-${ENVIRONMENT}"

# Get network config from Terraform state
echo_info "Retrieving network configuration from Terraform..."

cd terraform || { echo_error "Terraform directory not found"; exit 1; }

# Extract outputs from Terraform
SUBNET=$(terraform output -json 2>/dev/null | jq -r '.private_subnet_ids.value[0] // ""' 2>/dev/null || echo "")
SG=$(terraform output -json 2>/dev/null | jq -r '.ecs_tasks_security_group_id.value // ""' 2>/dev/null || echo "")

cd - > /dev/null

if [ -z "$SUBNET" ]; then
    echo_warn "Could not get subnet from Terraform, attempting AWS API lookup..."
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=${PROJECT_NAME}-vpc-${ENVIRONMENT}" --region $AWS_REGION --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "")
    if [ -z "$VPC_ID" ]; then
        echo_error "Could not find VPC"
        exit 1
    fi
    SUBNET=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region $AWS_REGION --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo "")
fi

if [ -z "$SUBNET" ]; then
    echo_error "Could not find private subnet"
    exit 1
fi
echo_success "Subnet: $SUBNET"

if [ -z "$SG" ]; then
    echo_warn "Could not get security group from Terraform, attempting AWS API lookup..."
    # Find ECS tasks security group
    VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Name,Values=${PROJECT_NAME}-vpc-${ENVIRONMENT}" --region $AWS_REGION --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo "")
    SG=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=${PROJECT_NAME}-ecs-tasks" --region $AWS_REGION --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "")
    if [ -z "$SG" ]; then
        # Last resort: get any security group from the VPC
        SG=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" --region $AWS_REGION --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "")
    fi
fi

if [ -z "$SG" ]; then
    echo_error "Could not find security group"
    exit 1
fi
echo_success "Security Group: $SG"

# Define loaders in execution order (from Terraform)
declare -a TIER_0=("stock_symbols")
declare -a TIER_1=("stock_prices_daily" "stock_prices_weekly" "stock_prices_monthly" "etf_prices_daily" "etf_prices_weekly" "etf_prices_monthly")
declare -a TIER_2=("company_profile" "analyst_sentiment" "analyst_upgrades_downgrades" "key_metrics" "seasonality" "market_indices" "econ_data" "aaiidata" "naaim_data" "feargreed" "earnings_history" "earnings_revisions" "earnings_surprise" "earnings_calendar")
declare -a TIER_3=("growth_metrics" "quality_metrics" "value_metrics")

declare -a ALL_TIERS=("${TIER_0[@]}" "${TIER_1[@]}" "${TIER_2[@]}" "${TIER_3[@]}")

echo ""
echo_info "Will trigger loaders in order:"
for tier in TIER_0 TIER_1 TIER_2 TIER_3; do
    declare -n arr=$tier
    for loader in "${arr[@]}"; do
        echo "  - $loader"
    done
done

echo ""
read -p "Proceed with manual trigger? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled"
    exit 0
fi

# ──────────────────────────────────────────────────────────────
# TIER 0: Stock symbols (no dependencies)
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "TIER 0: Loading stock symbols..."
for loader in "${TIER_0[@]}"; do
    TASK_DEF=$(aws ecs list-task-definitions --family-prefix "${PROJECT_NAME}-${loader}-loader" --region $AWS_REGION --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
    if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
        echo_warn "Task definition not found: ${PROJECT_NAME}-${loader}-loader"
        continue
    fi

    echo_info "  Triggering: $loader"
    TASK_ARN=$(aws ecs run-task \
        --cluster $ECS_CLUSTER \
        --task-definition "$TASK_DEF" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
        --region $AWS_REGION \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null || echo "")

    if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
        echo_error "  Failed to start task"
    else
        echo_success "  Task started: $TASK_ARN"
        # Wait a bit for task to start
        sleep 2
    fi
done

# Wait for Tier 0 to complete
echo_info "Waiting for Tier 0 tasks to complete (max 5 minutes)..."
sleep 300

# ──────────────────────────────────────────────────────────────
# TIER 1: Price data (depends on symbols)
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "TIER 1: Loading price data (6 loaders in parallel)..."
TIER1_TASKS=()
for loader in "${TIER_1[@]}"; do
    TASK_DEF=$(aws ecs list-task-definitions --family-prefix "${PROJECT_NAME}-${loader}-loader" --region $AWS_REGION --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
    if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
        echo_warn "Task definition not found: ${PROJECT_NAME}-${loader}-loader"
        continue
    fi

    echo_info "  Triggering: $loader"
    TASK_ARN=$(aws ecs run-task \
        --cluster $ECS_CLUSTER \
        --task-definition "$TASK_DEF" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
        --region $AWS_REGION \
        --query 'tasks[0].taskArn' \
        --output text 2>/dev/null || echo "")

    if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
        echo_error "  Failed to start task"
    else
        echo_success "  Task started"
        TIER1_TASKS+=("$TASK_ARN")
    fi
done

# Wait for Tier 1 to complete
echo_info "Waiting for Tier 1 tasks to complete (max 15 minutes)..."
sleep 900

# ──────────────────────────────────────────────────────────────
# TIER 2: Reference data
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "TIER 2: Loading reference data..."
for loader in "${TIER_2[@]}"; do
    TASK_DEF=$(aws ecs list-task-definitions --family-prefix "${PROJECT_NAME}-${loader}-loader" --region $AWS_REGION --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
    if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
        continue
    fi

    echo_info "  Triggering: $loader"
    aws ecs run-task \
        --cluster $ECS_CLUSTER \
        --task-definition "$TASK_DEF" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
        --region $AWS_REGION > /dev/null 2>&1 || echo_warn "  Failed to start"
done

echo_info "Waiting for Tier 2 tasks to complete (max 30 minutes)..."
sleep 1800

# ──────────────────────────────────────────────────────────────
# TIER 3: Computed metrics
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "TIER 3: Computing metrics..."
for loader in "${TIER_3[@]}"; do
    TASK_DEF=$(aws ecs list-task-definitions --family-prefix "${PROJECT_NAME}-${loader}-loader" --region $AWS_REGION --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
    if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
        continue
    fi

    echo_info "  Triggering: $loader"
    aws ecs run-task \
        --cluster $ECS_CLUSTER \
        --task-definition "$TASK_DEF" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
        --region $AWS_REGION > /dev/null 2>&1 || echo_warn "  Failed to start"
done

echo_info "Waiting for Tier 3 tasks to complete (max 30 minutes)..."
sleep 1800

echo ""
echo_success "All loaders triggered!"
echo ""
echo "Next: Check CloudWatch logs for execution status:"
echo "  aws logs tail /ecs/${PROJECT_NAME}-stock_symbols-loader --follow --region $AWS_REGION"
echo ""
