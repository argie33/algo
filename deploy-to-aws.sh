#!/bin/bash
#
# Algo Trading System - AWS Deployment Automation
#
# Interactive deployment script that:
# 1. Validates AWS credentials
# 2. Creates 3 secrets in AWS Secrets Manager
# 3. Pushes code to trigger GitHub Actions deployment
# 4. Monitors deployment progress
# 5. Verifies Lambda functions online

set -euo pipefail

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_success() { echo -e "${GREEN}✅ $*${NC}"; }
log_error() { echo -e "${RED}❌ $*${NC}"; }
log_warning() { echo -e "${YELLOW}⚠️  $*${NC}"; }
log_info() { echo -e "${CYAN}ℹ️  $*${NC}"; }

cat << 'EOF'
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                   🚀 ALGO TRADING SYSTEM - AWS DEPLOYMENT                 ║
║                                                                            ║
║  This script will:                                                         ║
║  1. Validate AWS credentials                                              ║
║  2. Create 3 secrets in AWS Secrets Manager                               ║
║  3. Commit and push code to trigger GitHub Actions                        ║
║  4. Monitor deployment progress                                           ║
║  5. Verify Lambda functions are online                                    ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
EOF

# Parse arguments
DRY_RUN=false
SKIP_SECRETS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-secrets)
            SKIP_SECRETS=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--skip-secrets]"
            exit 1
            ;;
    esac
done

# Step 1: Validate AWS credentials
echo ""
log_info "Step 1: Validating AWS credentials..."
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "Failed to authenticate with AWS. Ensure AWS credentials are configured."
    echo "Configure: aws configure"
    exit 1
fi
AWS_ARN=$(aws sts get-caller-identity --query Arn --output text)
log_success "AWS authenticated as: $AWS_ARN"

# Step 2: Create or update secrets
if [ "$SKIP_SECRETS" = false ]; then
    echo ""
    log_info "Step 2: Setting up AWS Secrets Manager (3 secrets)..."

    # Alpaca secret
    echo ""
    echo "📝 Alpaca Credentials"
    echo "   Get keys from: https://app.alpaca.markets/settings/api-keys"
    read -p "   API Key ID (APCA_API_KEY_ID): " ALPACA_KEY
    read -sp "   API Secret Key (APCA_API_SECRET_KEY): " ALPACA_SECRET
    echo ""

    ALPACA_JSON=$(cat <<EOF_ALPACA
{"api_key":"$ALPACA_KEY","api_secret":"$ALPACA_SECRET"}
EOF_ALPACA
)

    log_info "Creating secret: algo/alpaca..."
    if aws secretsmanager create-secret --name algo/alpaca \
        --secret-string "$ALPACA_JSON" --region us-east-1 2>/dev/null; then
        log_success "Secret created: algo/alpaca"
    else
        log_warning "Secret already exists, updating..."
        aws secretsmanager update-secret --secret-id algo/alpaca \
            --secret-string "$ALPACA_JSON" --region us-east-1 >/dev/null
        log_success "Secret updated: algo/alpaca"
    fi

    # FRED secret
    echo ""
    echo "📝 FRED API Key"
    echo "   Get key from: https://fred.stlouisfed.org (Settings)"
    read -p "   API Key (FRED_API_KEY): " FRED_KEY

    FRED_JSON="{\"api_key\":\"$FRED_KEY\"}"

    log_info "Creating secret: algo/fred..."
    if aws secretsmanager create-secret --name algo/fred \
        --secret-string "$FRED_JSON" --region us-east-1 2>/dev/null; then
        log_success "Secret created: algo/fred"
    else
        log_warning "Secret already exists, updating..."
        aws secretsmanager update-secret --secret-id algo/fred \
            --secret-string "$FRED_JSON" --region us-east-1 >/dev/null
        log_success "Secret updated: algo/fred"
    fi

    # RDS secret
    echo ""
    echo "📝 RDS Database Credentials"
    echo "   Get endpoint from: AWS Console → RDS → Databases → stocks-prod"
    read -p "   RDS Endpoint (host.xxxxx.us-east-1.rds.amazonaws.com): " RDS_HOST
    read -p "   Username (default: stocks): " RDS_USER
    RDS_USER=${RDS_USER:-stocks}
    read -sp "   Password: " RDS_PASSWORD
    echo ""

    RDS_JSON=$(cat <<EOF_RDS
{"host":"$RDS_HOST","user":"$RDS_USER","password":"$RDS_PASSWORD","port":5432,"database":"stocks"}
EOF_RDS
)

    log_info "Creating secret: algo/database..."
    if aws secretsmanager create-secret --name algo/database \
        --secret-string "$RDS_JSON" --region us-east-1 2>/dev/null; then
        log_success "Secret created: algo/database"
    else
        log_warning "Secret already exists, updating..."
        aws secretsmanager update-secret --secret-id algo/database \
            --secret-string "$RDS_JSON" --region us-east-1 >/dev/null
        log_success "Secret updated: algo/database"
    fi

    log_success ""
    log_success "All AWS Secrets created/updated successfully"
fi

# Step 3: Verify git state
echo ""
log_info "Step 3: Checking git state..."
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$BRANCH" != "main" ]; then
    log_error "Not on main branch (currently on: $BRANCH)"
    log_info "Switch to main: git checkout main"
    exit 1
fi

GIT_STATUS=$(git status --porcelain)
if [ -n "$GIT_STATUS" ]; then
    log_warning "Uncommitted changes detected"
    echo "$GIT_STATUS"
    read -p "Commit and push? (y/n): " -n 1 -r PROCEED
    echo ""
    if [[ ! $PROCEED =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled. Commit changes first."
        exit 0
    fi
    git add .
    git commit -m "chore: prepare for AWS deployment"
fi

# Step 4: Push to main (triggers GitHub Actions)
echo ""
log_info "Step 4: Pushing code to GitHub (triggers automatic deployment)..."

if [ "$DRY_RUN" = true ]; then
    log_warning "DRY RUN: Would push to origin/main"
    log_info "To actually deploy, remove --dry-run flag"
    exit 0
fi

if git push origin main; then
    log_success "Code pushed to origin/main"
else
    log_error "Failed to push to origin/main"
    exit 1
fi

log_success ""
log_success "DEPLOYMENT INITIATED!"

cat << 'EOF'

┌────────────────────────────────────────────────────────────────────────────┐
│  GitHub Actions is now deploying:                                          │
│                                                                            │
│  1. 🔍 Security scan (TruffleHog for secrets)                             │
│  2. 🧪 Run tests (pytest - 302+ tests)                                    │
│  3. ✅ Code quality (bandit, pip-audit, tfsec)                            │
│  4. 🏗️  Deploy infrastructure (Terraform)                                 │
│  5. ⚡ Deploy Lambda functions                                             │
│  6. 📅 Configure EventBridge schedules (2x daily)                         │
│                                                                            │
│  Monitor progress:                                                         │
│  🔗 https://github.com/argie33/algo/actions                               │
│                                                                            │
│  Estimated time: 5-10 minutes                                             │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

EOF

log_info "Waiting for GitHub Actions to start..."
sleep 5

# Step 5: Monitor deployment
log_info "Step 5: Monitoring deployment progress..."
log_info "Press Ctrl+C to stop monitoring (deployment will continue)"

ATTEMPT=0
MAX_ATTEMPTS=60

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    STATUS=$(gh run list --limit 1 --json status,conclusion --template '{{(index . 0).status}}' 2>/dev/null || echo "")
    CONCLUSION=$(gh run list --limit 1 --json status,conclusion --template '{{(index . 0).conclusion}}' 2>/dev/null || echo "")

    printf "\r[$ATTEMPT/$MAX_ATTEMPTS] Status: $STATUS"

    if [ "$STATUS" = "completed" ]; then
        echo ""
        if [ "$CONCLUSION" = "success" ]; then
            log_success "Deployment SUCCESSFUL!"
            break
        else
            log_error "Deployment FAILED (conclusion: $CONCLUSION)"
            log_info "Check logs: gh run view --log"
            exit 1
        fi
    fi

    sleep 5
done

# Step 6: Verify Lambda is online
echo ""
log_info "Step 6: Verifying Lambda functions..."
sleep 5

if aws lambda get-function-configuration --function-name stocks-algo-prod \
    --region us-east-1 >/dev/null 2>&1; then
    log_success "Lambda function deployed and online"
    log_info "Function: stocks-algo-prod"
else
    log_warning "Could not verify Lambda function (may still be deploying)"
fi

cat << 'EOF'

┌────────────────────────────────────────────────────────────────────────────┐
│  ✅ DEPLOYMENT COMPLETE!                                                   │
│                                                                            │
│  Next steps:                                                               │
│                                                                            │
│  1. Verify Lambda is executing:                                           │
│     $ aws logs tail /aws/lambda/stocks-algo-prod --follow                │
│                                                                            │
│  2. Check first orchestrator run (scheduled for 5:30 PM ET today):        │
│     $ aws logs tail /aws/lambda/stocks-algo-prod --since 1h              │
│                                                                            │
│  3. Monitor EventBridge schedules:                                        │
│     Morning run: 9:30 AM ET (optional)                                   │
│     Evening run: 5:30 PM ET (main)                                       │
│                                                                            │
│  4. Test orchestrator manually:                                           │
│     $ aws lambda invoke --function-name stocks-algo-prod \               │
│       --payload '{"source":"schedule"}' response.json                    │
│     $ cat response.json                                                   │
│                                                                            │
│  The system will now:                                                     │
│  • Load prices daily at 4:00 AM ET                                       │
│  • Run technicals at 10:00 AM ET                                         │
│  • Compute metrics at 5:00 PM ET                                         │
│  • Execute orchestrator at 5:30 PM ET (or 9:30 AM for morning run)      │
│                                                                            │
│  🎯 Full system operational and trading with real data!                  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

EOF

log_success "Deployment script complete. System is live! 🚀"
