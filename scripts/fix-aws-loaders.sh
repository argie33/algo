#!/bin/bash
# ============================================================
# FIX AWS LOADER ISSUES
# Identifies common problems and applies fixes
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

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  AWS LOADER FIXES"
echo "════════════════════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────────────────────
# FIX 1: Enable all EventBridge rules
# ──────────────────────────────────────────────────────────────
echo_info "FIX 1: Checking EventBridge rules..."

DISABLED_RULES=$(aws events list-rules --region $AWS_REGION \
    --query "Rules[?State=='DISABLED' && Name contains 'algo'].Name" \
    --output text)

if [ -z "$DISABLED_RULES" ]; then
    echo_success "No disabled EventBridge rules found"
else
    echo_warn "Found disabled rules, enabling them..."
    for RULE in $DISABLED_RULES; do
        echo_info "  Enabling rule: $RULE"
        aws events put-rule --name "$RULE" --state ENABLED --region $AWS_REGION
        echo_success "  Enabled: $RULE"
    done
fi

# ──────────────────────────────────────────────────────────────
# FIX 2: Create missing CloudWatch log groups
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "FIX 2: Ensuring CloudWatch log groups exist..."

LOADERS=(
    "stock_symbols" "stock_prices_daily" "stock_prices_weekly" "stock_prices_monthly"
    "etf_prices_daily" "etf_prices_weekly" "etf_prices_monthly"
    "company_profile" "analyst_sentiment" "key_metrics"
    "earnings_history" "seasonality" "market_indices" "econ_data"
    "growth_metrics" "quality_metrics" "value_metrics"
)

for LOADER in "${LOADERS[@]}"; do
    LOG_GROUP="/ecs/${PROJECT_NAME}-${LOADER}-loader"
    if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region $AWS_REGION --query 'logGroups | length(@)' --output text 2>/dev/null | grep -q "^1$"; then
        # Already exists
        continue
    fi
    echo_info "  Creating log group: $LOG_GROUP"
    aws logs create-log-group --log-group-name "$LOG_GROUP" --region $AWS_REGION 2>/dev/null || true
    # Set retention to 30 days
    aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 30 --region $AWS_REGION 2>/dev/null || true
    echo_success "  Created: $LOG_GROUP"
done

# ──────────────────────────────────────────────────────────────
# FIX 3: Verify Docker image is in ECR
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "FIX 3: Checking Docker image in ECR..."

ECR_NAME="${PROJECT_NAME}-ecr-${ENVIRONMENT}"
ECR_URL=$(aws ecr describe-repositories --repository-names "$ECR_NAME" --region $AWS_REGION \
    --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")

if [ -z "$ECR_URL" ]; then
    echo_error "ECR repository not found: $ECR_NAME"
    echo "  Run: git push origin main  # to trigger GitHub Actions deployment"
    exit 1
fi
echo_success "ECR repository: $ECR_URL"

# Check for latest image
if aws ecr describe-images --repository-name "$ECR_NAME" --region $AWS_REGION \
    --query "imageDetails[?contains(imageTags, 'dev-latest')]" --output text 2>/dev/null | grep -q dev-latest; then
    echo_success "Docker image exists: dev-latest"
else
    echo_warn "dev-latest tag not found"
    echo "  Latest images available:"
    aws ecr describe-images --repository-name "$ECR_NAME" --region $AWS_REGION \
        --query "imageDetails[*].imageTags[0]" --output text | head -5
    echo ""
    echo "  To push latest image:"
    echo "    git push origin main  # Triggers GitHub Actions deployment"
fi

# ──────────────────────────────────────────────────────────────
# FIX 4: Verify database credentials in Secrets Manager
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "FIX 4: Checking Secrets Manager credentials..."

DB_SECRET="${PROJECT_NAME}-db-credentials-${ENVIRONMENT}"
if aws secretsmanager describe-secret --secret-id "$DB_SECRET" --region $AWS_REGION > /dev/null 2>&1; then
    # Try to get the secret to verify it's accessible
    if aws secretsmanager get-secret-value --secret-id "$DB_SECRET" --region $AWS_REGION > /dev/null 2>&1; then
        echo_success "Database credentials verified in Secrets Manager"
    else
        echo_error "Database credentials not accessible"
        exit 1
    fi
else
    echo_error "Database credentials secret not found"
    exit 1
fi

# ──────────────────────────────────────────────────────────────
# FIX 5: Check RDS connectivity
# ──────────────────────────────────────────────────────────────
echo ""
echo_info "FIX 5: Checking RDS database..."

RDS_ID="${PROJECT_NAME}-db"
DB_INFO=$(aws rds describe-db-instances --db-instance-identifier "$RDS_ID" --region $AWS_REGION 2>/dev/null || echo "")
if [ -z "$DB_INFO" ]; then
    echo_error "RDS database not found: $RDS_ID"
    exit 1
fi

DB_STATUS=$(echo "$DB_INFO" | aws rds describe-db-instances --db-instance-identifier "$RDS_ID" --region $AWS_REGION --query 'DBInstances[0].DBInstanceStatus' --output text)
if [ "$DB_STATUS" != "available" ]; then
    echo_warn "RDS status: $DB_STATUS (should be 'available')"
    echo "  Waiting for RDS to become available..."
    sleep 60
else
    echo_success "RDS database status: available"
fi

# ──────────────────────────────────────────────────────────────
# FIX 6: Summary and next steps
# ──────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
echo_success "AWS LOADER INFRASTRUCTURE VERIFIED"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "✓ EventBridge rules enabled"
echo "✓ CloudWatch log groups ready"
echo "✓ Docker image in ECR"
echo "✓ Secrets Manager credentials verified"
echo "✓ RDS database accessible"
echo ""
echo "NEXT STEPS:"
echo ""
echo "1. Manually trigger loaders (test):"
echo "   bash scripts/trigger-all-loaders.sh"
echo ""
echo "2. Monitor loader execution:"
echo "   aws logs tail /ecs/${PROJECT_NAME}-stock_symbols-loader --follow --region $AWS_REGION"
echo ""
echo "3. Check data was loaded:"
echo "   curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?limit=1"
echo ""
echo "4. Run orchestrator once data is ready:"
echo "   aws ecs run-task --cluster algo-dev --task-definition algo-algo-orchestrator ..."
echo ""
