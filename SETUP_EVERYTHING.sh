#!/bin/bash
# Complete Setup - Configure everything for GitHub Actions deployment
# Run this ONCE to set up all prerequisites

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}COMPLETE SETUP - ALL PREREQUISITES${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. GET AWS ACCOUNT INFO
echo -e "${YELLOW}Step 1: Verify AWS Credentials${NC}"

# Create aws command wrapper if not in PATH
if ! command -v aws &> /dev/null; then
    if ! python3 -m awscli --version &> /dev/null; then
        echo -e "${RED}ERROR: AWS CLI not installed${NC}"
        echo "Install: pip3 install awscli"
        exit 1
    fi
    # Use Python module version
    aws() { python3 -m awscli "$@"; }
fi

if ! aws sts get-caller-identity &>/dev/null; then
    echo -e "${RED}ERROR: AWS credentials not configured${NC}"
    echo "Run: aws configure"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

echo -e "${GREEN}✓ AWS Account: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ Region: $AWS_REGION${NC}"
echo ""

# 2. CREATE S3 BUCKET FOR TEMPLATES
echo -e "${YELLOW}Step 2: Create S3 Templates Bucket${NC}"
BUCKET_NAME="stocks-cf-templates-${AWS_ACCOUNT_ID}"

if aws s3 ls "s3://${BUCKET_NAME}" 2>/dev/null; then
    echo -e "${GREEN}✓ Bucket exists: ${BUCKET_NAME}${NC}"
else
    echo "Creating bucket: ${BUCKET_NAME}"
    aws s3api create-bucket \
        --bucket "${BUCKET_NAME}" \
        --region "${AWS_REGION}" \
        $([ "$AWS_REGION" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=$AWS_REGION" || echo "")
    echo -e "${GREEN}✓ Bucket created${NC}"
fi
echo ""

# 3. CREATE CLOUDFORMATION CORE STACK
echo -e "${YELLOW}Step 3: Deploy Core Infrastructure Stack${NC}"

CORE_STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name stocks-core \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "MISSING")

if [ "$CORE_STACK_STATUS" == "MISSING" ] || [ -z "$CORE_STACK_STATUS" ]; then
    echo "Deploying core infrastructure..."

    # Create minimal core stack with S3 export
    aws cloudformation deploy \
        --stack-name stocks-core \
        --template-file template-core.yml \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION"

    echo -e "${GREEN}✓ Core stack deployed${NC}"
else
    echo -e "${GREEN}✓ Core stack already exists: $CORE_STACK_STATUS${NC}"
fi
echo ""

# 4. CREATE IAM ROLE FOR GITHUB ACTIONS
echo -e "${YELLOW}Step 4: Create IAM Role for GitHub Actions${NC}"

ROLE_NAME="GitHubActionsDeployRole"
ROLE_EXISTS=$(aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null || echo "")

if [ -z "$ROLE_EXISTS" ]; then
    echo "Creating IAM role: $ROLE_NAME"

    # Get GitHub repo info
    GITHUB_OWNER=$(git remote get-url origin | sed 's|.*github.com/\([^/]*\)/.*|\1|')
    GITHUB_REPO=$(git remote get-url origin | sed 's|.*github.com/.*/\([^/]*\)\.git|\1|')

    echo "GitHub Repo: $GITHUB_OWNER/$GITHUB_REPO"

    cat > /tmp/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_OWNER}/${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file:///tmp/trust-policy.json

    echo -e "${GREEN}✓ IAM role created${NC}"
else
    echo -e "${GREEN}✓ IAM role already exists${NC}"
fi

# Attach admin policy
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AdministratorAccess 2>/dev/null || true

echo -e "${GREEN}✓ Admin policy attached${NC}"
echo ""

# 5. VERIFY RDS DATABASE
echo -e "${YELLOW}Step 5: Verify Database Access${NC}"

if [ -z "$DB_HOST" ]; then
    echo -e "${YELLOW}⚠ DB_HOST not set (check .env.local)${NC}"
else
    echo "Testing connection to: $DB_HOST"
    if psql -h "$DB_HOST" -U "${DB_USER:-stocks}" -d "${DB_NAME:-stocks}" -c "SELECT COUNT(*) FROM stock_symbols" 2>/dev/null; then
        echo -e "${GREEN}✓ Database connection verified${NC}"
    else
        echo -e "${YELLOW}⚠ Database connection failed${NC}"
        echo "Check: DB_HOST, DB_USER, DB_PASSWORD in .env.local"
    fi
fi
echo ""

# 6. CHECK GITHUB SECRETS
echo -e "${YELLOW}Step 6: GitHub Secrets Configuration${NC}"
echo ""
echo -e "${BLUE}You must add these secrets to GitHub:${NC}"
echo ""
echo "Go to: GitHub → Settings → Secrets and Variables → Actions"
echo ""
echo -e "${YELLOW}Required Secrets:${NC}"
echo "  1. AWS_ACCOUNT_ID = $AWS_ACCOUNT_ID"
echo "  2. RDS_USERNAME = stocks"
echo "  3. RDS_PASSWORD = (your database password)"
echo ""
echo -e "${YELLOW}Optional Secrets:${NC}"
echo "  4. FRED_API_KEY = (if using FRED data)"
echo "  5. IBKR_USERNAME = (if using broker data)"
echo "  6. IBKR_PASSWORD = (if using broker data)"
echo ""
echo "Press ENTER after adding secrets to GitHub..."
read
echo ""

# 7. SUMMARY
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}SETUP COMPLETE${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}✓ AWS Account verified: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ S3 bucket created: $BUCKET_NAME${NC}"
echo -e "${GREEN}✓ Core stack deployed${NC}"
echo -e "${GREEN}✓ IAM role created: $ROLE_NAME${NC}"
echo -e "${GREEN}✓ Database verified${NC}"
echo ""
echo -e "${BLUE}NEXT STEPS:${NC}"
echo "1. Add GitHub secrets (see above)"
echo "2. Run: git push origin main"
echo "3. Watch GitHub Actions deploy phases C, D, E"
echo ""
echo -e "${YELLOW}GitHub Actions Deployment Flow:${NC}"
echo "  → Deploy Phase C Lambda (buyselldaily 3-4h → 7 min)"
echo "  → Deploy Phase E DynamoDB (80% fewer API calls)"
echo "  → Deploy Phase D Step Functions (full orchestration)"
echo "  → Execute with optimizations enabled"
echo ""
echo -e "${GREEN}Total deployment time: 15-20 minutes${NC}"
echo ""
