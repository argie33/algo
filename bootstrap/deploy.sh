#!/bin/bash
# ============================================================
# Terraform Infrastructure Deployment Script
# Purpose: Automated deployment of stocks analytics infrastructure
# ============================================================

set -e

echo "🚀 Stocks Analytics Infrastructure Deployment"
echo "============================================================"

# Configuration
AWS_REGION="us-east-1"
PROJECT_NAME="stocks"
GITHUB_ORG="argeropolos"
GITHUB_REPO="algo"
AWS_ACCOUNT_ID="626216981288"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================
# Step 1: Verify Prerequisites
# ============================================================
echo ""
echo -e "${YELLOW}Step 1: Verifying Prerequisites${NC}"
echo "============================================================"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found${NC}"
    echo "   Install from: https://aws.amazon.com/cli/"
    exit 1
fi
echo "✅ AWS CLI: $(aws --version)"

# Check GitHub CLI
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI not found${NC}"
    echo "   Install from: https://cli.github.com/"
    exit 1
fi
echo "✅ GitHub CLI: $(gh --version)"

# Check git
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git not found${NC}"
    exit 1
fi
echo "✅ Git: $(git --version)"

# Check AWS credentials
echo ""
echo "Verifying AWS credentials..."
if ! IDENTITY=$(aws sts get-caller-identity --region "$AWS_REGION" 2>/dev/null); then
    echo -e "${RED}❌ AWS credentials not configured${NC}"
    echo "   Run: aws configure"
    exit 1
fi
ACTUAL_ACCOUNT=$(echo "$IDENTITY" | jq -r '.Account')
echo "✅ AWS Account: $ACTUAL_ACCOUNT"

if [ "$ACTUAL_ACCOUNT" != "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Wrong AWS account!${NC}"
    echo "   Expected: $AWS_ACCOUNT_ID"
    echo "   Got: $ACTUAL_ACCOUNT"
    exit 1
fi

# ============================================================
# Step 2: Bootstrap OIDC Stack
# ============================================================
echo ""
echo -e "${YELLOW}Step 2: Deploying Bootstrap OIDC Stack${NC}"
echo "============================================================"

OIDC_STACK_NAME="stocks-oidc"

STACK_STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$OIDC_STACK_NAME" \
    --region "$AWS_REGION" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "MISSING")

if [[ "$STACK_STATUS" == *"COMPLETE"* ]]; then
    echo "✅ OIDC Stack already deployed: $STACK_STATUS"
else
    echo "⏳ Deploying OIDC stack (this creates the github-actions-role)..."
    
    aws cloudformation deploy \
        --template-file bootstrap/oidc.yml \
        --stack-name "$OIDC_STACK_NAME" \
        --region "$AWS_REGION" \
        --parameter-overrides \
            ProjectName="$PROJECT_NAME" \
            GitHubOrg="$GITHUB_ORG" \
            GitHubRepo="$GITHUB_REPO" \
        --capabilities CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset
    
    echo "✅ OIDC stack deployed"
fi

# Verify role exists
if aws iam get-role --role-name github-actions-role &>/dev/null; then
    echo "✅ GitHub Actions role verified"
else
    echo -e "${RED}❌ GitHub Actions role not found${NC}"
    exit 1
fi

# ============================================================
# Step 3: Set GitHub Secrets
# ============================================================
echo ""
echo -e "${YELLOW}Step 3: Configuring GitHub Secrets${NC}"
echo "============================================================"

echo "⏳ Setting GitHub secrets..."

# AWS_ACCOUNT_ID
gh secret set AWS_ACCOUNT_ID --body "$AWS_ACCOUNT_ID" 2>/dev/null && echo "✅ AWS_ACCOUNT_ID" || echo "⚠️  AWS_ACCOUNT_ID"

# AWS_ACCESS_KEY_ID
read -sp "Enter AWS Access Key ID: " AWS_ACCESS_KEY_ID
echo ""
gh secret set AWS_ACCESS_KEY_ID --body "$AWS_ACCESS_KEY_ID" && echo "✅ AWS_ACCESS_KEY_ID" || echo "❌ Failed to set AWS_ACCESS_KEY_ID"

# AWS_SECRET_ACCESS_KEY
read -sp "Enter AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
echo ""
gh secret set AWS_SECRET_ACCESS_KEY --body "$AWS_SECRET_ACCESS_KEY" && echo "✅ AWS_SECRET_ACCESS_KEY" || echo "❌ Failed to set AWS_SECRET_ACCESS_KEY"

# RDS_PASSWORD
read -sp "Enter RDS Password (min 8 chars): " RDS_PASSWORD
echo ""
if [ ${#RDS_PASSWORD} -lt 8 ]; then
    echo -e "${RED}❌ RDS password must be at least 8 characters${NC}"
    exit 1
fi
gh secret set RDS_PASSWORD --body "$RDS_PASSWORD" && echo "✅ RDS_PASSWORD" || echo "❌ Failed to set RDS_PASSWORD"

# SLACK_WEBHOOK (optional)
echo ""
read -p "Enter Slack webhook URL (optional, press Enter to skip): " SLACK_WEBHOOK
if [ ! -z "$SLACK_WEBHOOK" ]; then
    gh secret set SLACK_WEBHOOK --body "$SLACK_WEBHOOK" && echo "✅ SLACK_WEBHOOK" || echo "❌ Failed to set SLACK_WEBHOOK"
fi

echo ""
echo "✅ GitHub secrets configured"

# ============================================================
# Step 4: Push to GitHub
# ============================================================
echo ""
echo -e "${YELLOW}Step 4: Pushing Code to GitHub${NC}"
echo "============================================================"

git add bootstrap/ terraform/ TERRAFORM_*.md
git commit -m "Infrastructure: Bootstrap OIDC, finalize Terraform deployment" 2>/dev/null || echo "ℹ️  No changes to commit"

echo "⏳ Pushing to GitHub..."
git push origin main

echo "✅ Code pushed"

# ============================================================
# Step 5: Monitor Deployment
# ============================================================
echo ""
echo -e "${YELLOW}Step 5: Monitoring Deployment${NC}"
echo "============================================================"

echo ""
echo "🔗 Watch deployment progress:"
echo "   https://github.com/$GITHUB_ORG/$GITHUB_REPO/actions"
echo ""
echo "⏱️  Expected deployment time: 15-20 minutes"
echo ""
echo "Once complete, verify with:"
echo "   aws cloudformation describe-stacks --stack-name stocks-dev --query 'Stacks[0].Outputs' --region $AWS_REGION"
echo ""
echo -e "${GREEN}✅ Deployment initiated!${NC}"
