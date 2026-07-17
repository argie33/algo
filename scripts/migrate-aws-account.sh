#!/bin/bash
# ============================================================
# AWS Account Migration Automation Script
# Migrates from edgebrookecapital@gmail.com to edgebrookelabs@gmail.com
# ============================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================
# PHASE 1: Setup & Validation
# ============================================================

phase_setup() {
    log_info "Phase 1: Setup & Validation"

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Install via: pip install awscli"
        exit 1
    fi

    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform not found. Install from: https://www.terraform.io/downloads"
        exit 1
    fi

    # Check jq
    if ! command -v jq &> /dev/null; then
        log_warning "jq not found. Installing recommended dependency..."
    fi

    # Check root credentials
    log_info "Validating root credentials..."
    if ! AWS_PROFILE=root aws sts get-caller-identity &> /dev/null; then
        log_error "Root AWS profile not configured or invalid"
        log_info "Configure with: aws configure --profile root"
        exit 1
    fi

    ROOT_ACCOUNT_ID=$(AWS_PROFILE=root aws sts get-caller-identity --query Account -o text)
    log_success "Root credentials validated (Account: $ROOT_ACCOUNT_ID)"

    # Verify Organizations is enabled
    log_info "Checking AWS Organizations..."
    if ! AWS_PROFILE=root aws organizations describe-organization &> /dev/null; then
        log_error "AWS Organizations not enabled or no permission"
        log_info "Enable at: https://console.aws.amazon.com/organizations"
        exit 1
    fi

    log_success "AWS Organizations enabled"
}

# ============================================================
# PHASE 2: Create New Account
# ============================================================

phase_create_account() {
    log_info "Phase 2: Create New Account via Terraform"

    cd terraform/accounts

    log_info "Initializing Terraform (account creation)..."
    AWS_PROFILE=root terraform init

    log_info "Planning account creation..."
    AWS_PROFILE=root terraform plan -out=plan.out

    read -p "Create new account? (y/N) " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warning "Account creation cancelled"
        exit 1
    fi

    log_info "Executing account creation..."
    AWS_PROFILE=root terraform apply plan.out

    # Save outputs
    AWS_PROFILE=root terraform output -json > migration-state.json

    NEW_ACCOUNT_ID=$(jq -r '.new_account_id.value' migration-state.json)
    SNAPSHOT_ID=$(jq -r '.rds_snapshot_id.value' migration-state.json)
    ROLE_ARN=$(jq -r '.cross_account_role_arn.value' migration-state.json)

    log_success "New account created: $NEW_ACCOUNT_ID"
    log_success "RDS snapshot: $SNAPSHOT_ID"
    log_success "Cross-account role: $ROLE_ARN"

    cd - > /dev/null
}

# ============================================================
# PHASE 3: Wait for RDS Snapshot
# ============================================================

phase_wait_snapshot() {
    log_info "Phase 3: Wait for RDS Snapshot"

    SNAPSHOT_ID=$1

    log_info "Waiting for RDS snapshot to complete..."

    timeout=900  # 15 minutes
    elapsed=0

    while [ $elapsed -lt $timeout ]; do
        STATUS=$(AWS_PROFILE=root aws rds describe-db-snapshots \
            --db-snapshot-identifier "$SNAPSHOT_ID" \
            --query "DBSnapshots[0].Status" -o text 2>/dev/null || echo "error")

        PROGRESS=$(AWS_PROFILE=root aws rds describe-db-snapshots \
            --db-snapshot-identifier "$SNAPSHOT_ID" \
            --query "DBSnapshots[0].PercentProgress" -o text 2>/dev/null || echo "0")

        if [ "$STATUS" = "available" ]; then
            log_success "RDS snapshot ready ($PROGRESS%)"
            return 0
        fi

        log_info "Snapshot status: $STATUS ($PROGRESS%) - elapsed ${elapsed}s"
        sleep 10
        ((elapsed += 10))
    done

    log_error "RDS snapshot timed out after 15 minutes"
    exit 1
}

# ============================================================
# PHASE 4: Assume Role in New Account
# ============================================================

phase_assume_role() {
    log_info "Phase 4: Assume Role in New Account"

    ROLE_ARN=$1

    log_info "Assuming cross-account role..."

    CREDS=$(AWS_PROFILE=root aws sts assume-role \
        --role-arn "$ROLE_ARN" \
        --role-session-name "terraform-migration" \
        --output json)

    export AWS_ACCESS_KEY_ID=$(echo "$CREDS" | jq -r '.Credentials.AccessKeyId')
    export AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | jq -r '.Credentials.SecretAccessKey')
    export AWS_SESSION_TOKEN=$(echo "$CREDS" | jq -r '.Credentials.SessionToken')
    export AWS_ACCOUNT_ID=$(echo "$CREDS" | jq -r '.AssumedRoleUser.Arn' | cut -d: -f5)

    log_success "Assumed role in new account: $AWS_ACCOUNT_ID"

    # Verify
    VERIFY_ACCOUNT=$(aws sts get-caller-identity --query Account -o text)
    if [ "$VERIFY_ACCOUNT" = "$AWS_ACCOUNT_ID" ]; then
        log_success "Verified access to new account"
    else
        log_error "Failed to verify access to new account"
        exit 1
    fi
}

# ============================================================
# PHASE 5: Restore RDS Snapshot
# ============================================================

phase_restore_rds() {
    log_info "Phase 5: Restore RDS Snapshot in New Account"

    SNAPSHOT_ID=$1

    log_info "Restoring RDS snapshot: $SNAPSHOT_ID"

    aws rds restore-db-instance-from-db-snapshot \
        --db-instance-identifier algo-db \
        --db-snapshot-identifier "$SNAPSHOT_ID" \
        --db-instance-class db.t4g.small \
        --multi-az false \
        --publicly-accessible false \
        --storage-encrypted true \
        --region us-east-1 \
        --no-cli-pager

    log_success "RDS restore initiated"

    log_info "Waiting for RDS restore (this takes 5-10 minutes)..."

    timeout=600  # 10 minutes
    elapsed=0

    while [ $elapsed -lt $timeout ]; do
        STATUS=$(aws rds describe-db-instances \
            --db-instance-identifier algo-db \
            --query "DBInstances[0].DBInstanceStatus" -o text 2>/dev/null || echo "error")

        if [ "$STATUS" = "available" ]; then
            RDS_ENDPOINT=$(aws rds describe-db-instances \
                --db-instance-identifier algo-db \
                --query "DBInstances[0].Endpoint.Address" -o text)

            log_success "RDS restored and available at: $RDS_ENDPOINT"
            echo "$RDS_ENDPOINT" > /tmp/rds_endpoint.txt
            return 0
        fi

        log_info "RDS status: $STATUS - elapsed ${elapsed}s"
        sleep 10
        ((elapsed += 10))
    done

    log_error "RDS restore timed out after 10 minutes"
    exit 1
}

# ============================================================
# PHASE 6: Deploy Infrastructure
# ============================================================

phase_deploy_infrastructure() {
    log_info "Phase 6: Deploy Infrastructure to New Account"

    NEW_ACCOUNT_ID=$1

    cd terraform/new-account

    # Prepare tfvars
    log_info "Preparing terraform.tfvars..."
    cp terraform.tfvars.example terraform.tfvars
    sed -i "s/XXXXXXXXXX/$NEW_ACCOUNT_ID/g" terraform.tfvars

    log_info "Initializing Terraform..."
    terraform init \
        -backend-config="bucket=algo-terraform-state-$NEW_ACCOUNT_ID" \
        -backend-config="key=stocks/terraform.tfstate" \
        -backend-config="region=us-east-1" \
        -backend-config="encrypt=true" \
        -backend-config="dynamodb_table=algo-terraform-locks"

    log_info "Planning infrastructure deployment..."
    terraform plan -var-file=terraform.tfvars -out=plan.out

    read -p "Deploy infrastructure to new account? (y/N) " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warning "Deployment cancelled"
        exit 1
    fi

    log_info "Deploying infrastructure (this takes 10-20 minutes)..."
    terraform apply plan.out

    log_success "Infrastructure deployed successfully"

    # Save outputs
    terraform output -json > infrastructure-state.json

    cd - > /dev/null
}

# ============================================================
# PHASE 7: Verify Deployment
# ============================================================

phase_verify() {
    log_info "Phase 7: Verify Deployment"

    log_info "Checking API Gateway..."
    API_ENDPOINT=$(aws apigatewayv2 get-apis \
        --query "Apis[?Name=='algo-api-dev'].ApiEndpoint" -o text)

    if [ -z "$API_ENDPOINT" ]; then
        log_warning "API Gateway not found"
    else
        log_success "API Gateway: $API_ENDPOINT"

        log_info "Testing API health endpoint..."
        HEALTH=$(curl -s "$API_ENDPOINT/api/health" | jq -r '.status' 2>/dev/null || echo "error")
        if [ "$HEALTH" = "ok" ]; then
            log_success "API is healthy"
        else
            log_warning "API health check inconclusive"
        fi
    fi

    log_info "Checking RDS..."
    RDS_ENDPOINT=$(cat /tmp/rds_endpoint.txt 2>/dev/null || echo "unknown")
    log_success "RDS endpoint: $RDS_ENDPOINT"

    log_info "Checking Lambda functions..."
    LAMBDA_COUNT=$(aws lambda list-functions --query "length(Functions)" -o text)
    log_success "Lambda functions: $LAMBDA_COUNT"

    log_info "Checking ECS cluster..."
    CLUSTER_COUNT=$(aws ecs list-clusters --query "length(clusterArns)" -o text)
    log_success "ECS clusters: $CLUSTER_COUNT"
}

# ============================================================
# PHASE 8: Close Old Account
# ============================================================

phase_close_old_account() {
    log_warning "Phase 8: Close Old Account (IRREVERSIBLE)"

    read -p "Close old account 626216981288 (edgebrookecapital@gmail.com)? Type 'yes' to confirm: " -r
    if [ "$REPLY" != "yes" ]; then
        log_warning "Account closure cancelled"
        return
    fi

    log_warning "Closing old account..."
    AWS_PROFILE=root aws organizations close-account --account-id 626216981288

    log_success "Old account marked for closure"
    log_info "Account will be fully deleted in 90 days"
    log_info "You have 90 days to contact AWS Support to reactivate if needed"
}

# ============================================================
# Main Execution
# ============================================================

main() {
    log_info "Starting AWS Account Migration"
    log_info "Old Account: 626216981288 (edgebrookecapital@gmail.com)"
    log_info "New Account: edgebrookelabs@gmail.com (via Organizations)"

    # Execute phases
    phase_setup
    phase_create_account

    # Extract values from migration state
    NEW_ACCOUNT_ID=$(jq -r '.new_account_id.value' terraform/accounts/migration-state.json)
    SNAPSHOT_ID=$(jq -r '.rds_snapshot_id.value' terraform/accounts/migration-state.json)
    ROLE_ARN=$(jq -r '.cross_account_role_arn.value' terraform/accounts/migration-state.json)

    phase_wait_snapshot "$SNAPSHOT_ID"
    phase_assume_role "$ROLE_ARN"
    phase_restore_rds "$SNAPSHOT_ID"
    phase_deploy_infrastructure "$NEW_ACCOUNT_ID"
    phase_verify
    phase_close_old_account

    log_success "============================================"
    log_success "Migration Complete!"
    log_success "============================================"
    log_info "New Account ID: $NEW_ACCOUNT_ID"
    log_info "Email: edgebrookelabs@gmail.com"
    log_info "Next: Test dashboard, verify data, monitor loaders"
}

# Run main
main "$@"
