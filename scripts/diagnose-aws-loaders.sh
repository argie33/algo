#!/bin/bash
# ============================================================
# DIAGNOSE AWS LOADER ISSUES
# Checks infrastructure, triggers loaders, monitors CloudWatch
# ============================================================

set -e  # Exit on any error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info() { echo -e "${BLUE}ℹ${NC} $1"; }
echo_success() { echo -e "${GREEN}✅${NC} $1"; }
echo_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
echo_error() { echo -e "${RED}❌${NC} $1"; }

AWS_REGION="us-east-1"
PROJECT_NAME="algo"
ENVIRONMENT="dev"

# ──────────────────────────────────────────────────────────────
# PHASE 1: CHECK BASIC AWS ACCESS
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 1: Checking AWS access..."

if ! aws sts get-caller-identity --region $AWS_REGION > /dev/null 2>&1; then
    echo_error "AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi
echo_success "AWS credentials configured"

# ──────────────────────────────────────────────────────────────
# PHASE 2: CHECK INFRASTRUCTURE
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 2: Checking infrastructure..."

# Check RDS
RDS_ID="${PROJECT_NAME}-db"
if aws rds describe-db-instances --db-instance-identifier $RDS_ID --region $AWS_REGION > /dev/null 2>&1; then
    DB_STATUS=$(aws rds describe-db-instances --db-instance-identifier $RDS_ID --region $AWS_REGION --query 'DBInstances[0].DBInstanceStatus' --output text)
    if [ "$DB_STATUS" = "available" ]; then
        echo_success "RDS database: $DB_STATUS"
    else
        echo_warn "RDS database status: $DB_STATUS (may not be ready)"
    fi
else
    echo_error "RDS database not found"
    exit 1
fi

# Check ECR
ECR_NAME="${PROJECT_NAME}-ecr-${ENVIRONMENT}"
ECR_URL=$(aws ecr describe-repositories --region $AWS_REGION --query "repositories[?repositoryName=='${ECR_NAME}'].repositoryUri" --output text 2>/dev/null || echo "")
if [ -z "$ECR_URL" ]; then
    echo_error "ECR repository not found"
    exit 1
fi
echo_success "ECR repository: $ECR_URL"

# Check if image exists
IMAGE_TAG="dev-latest"
if aws ecr describe-images --repository-name $ECR_NAME --image-ids "imageTag=$IMAGE_TAG" --region $AWS_REGION > /dev/null 2>&1; then
    echo_success "Docker image exists: $IMAGE_TAG"
else
    echo_warn "Docker image not found: $IMAGE_TAG"
    echo "   You may need to push a new image"
fi

# Check ECS cluster
ECS_CLUSTER="${PROJECT_NAME}-${ENVIRONMENT}"
if aws ecs describe-clusters --clusters $ECS_CLUSTER --region $AWS_REGION --query 'clusters[0].clusterName' --output text > /dev/null 2>&1; then
    echo_success "ECS cluster exists: $ECS_CLUSTER"
else
    echo_error "ECS cluster not found: $ECS_CLUSTER"
    exit 1
fi

# ──────────────────────────────────────────────────────────────
# PHASE 3: CHECK EVENTBRIDGE RULES
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 3: Checking EventBridge rules..."

RULES=$(aws events list-rules --region $AWS_REGION --query "Rules[?Name contains 'algo'].Name" --output text | wc -w)
if [ "$RULES" -gt 0 ]; then
    echo_success "Found $RULES EventBridge rules"

    # Check if any are disabled
    DISABLED=$(aws events list-rules --region $AWS_REGION --query "Rules[?State=='DISABLED' && Name contains 'algo'].Name" --output text | wc -w)
    if [ "$DISABLED" -gt 0 ]; then
        echo_warn "Found $DISABLED disabled rules"
    fi
else
    echo_error "No EventBridge rules found"
fi

# ──────────────────────────────────────────────────────────────
# PHASE 4: CHECK SECRETS MANAGER
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 4: Checking Secrets Manager..."

DB_SECRET="${PROJECT_NAME}-db-credentials-${ENVIRONMENT}"
if aws secretsmanager describe-secret --secret-id $DB_SECRET --region $AWS_REGION > /dev/null 2>&1; then
    echo_success "Database credentials secret exists"
else
    echo_error "Database credentials secret not found"
    exit 1
fi

ALGO_SECRET="${PROJECT_NAME}-algo-secrets-${ENVIRONMENT}"
if aws secretsmanager describe-secret --secret-id $ALGO_SECRET --region $AWS_REGION > /dev/null 2>&1; then
    echo_success "Algo secrets secret exists"
else
    echo_error "Algo secrets secret not found"
fi

# ──────────────────────────────────────────────────────────────
# PHASE 5: CHECK CLOUDWATCH LOG GROUPS
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 5: Checking CloudWatch log groups..."

LOG_GROUP="/ecs/${PROJECT_NAME}-stock_symbols-loader"
if aws logs describe-log-groups --log-group-name-prefix "/ecs/${PROJECT_NAME}-" --region $AWS_REGION --query 'logGroups | length(@)' --output text > /dev/null 2>&1; then
    echo_success "CloudWatch log groups exist"
else
    echo_warn "CloudWatch log groups may not exist yet"
fi

# ──────────────────────────────────────────────────────────────
# PHASE 6: ATTEMPT MANUAL LOADER TRIGGER
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "PHASE 6: Checking if loaders can be triggered..."

# Get a loader task definition
TASK_DEF=$(aws ecs list-task-definitions --family-prefix "${PROJECT_NAME}-stock_symbols-loader" --region $AWS_REGION --query 'taskDefinitionArns[0]' --output text 2>/dev/null || echo "")
if [ -z "$TASK_DEF" ] || [ "$TASK_DEF" = "None" ]; then
    echo_error "No loader task definitions found"
    exit 1
fi
echo_success "Loader task definition found: $TASK_DEF"

# ──────────────────────────────────────────────────────────────
# PHASE 7: STATUS SUMMARY
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "SUMMARY: Infrastructure check complete"
echo ""
echo "Next steps:"
echo "  1. To trigger stock_symbols loader manually:"
echo "     aws ecs run-task --cluster $ECS_CLUSTER --task-definition ${TASK_DEF} --launch-type FARGATE --network-configuration awsvpcConfiguration={subnets=[SUBNET_ID],securityGroups=[SG_ID],assignPublicIp=DISABLED} --region $AWS_REGION"
echo ""
echo "  2. To watch CloudWatch logs:"
echo "     aws logs tail /ecs/${PROJECT_NAME}-stock_symbols-loader --follow --region $AWS_REGION"
echo ""
echo "  3. To check loader execution status:"
echo "     aws ecs list-tasks --cluster $ECS_CLUSTER --launch-type FARGATE --region $AWS_REGION"
echo ""
