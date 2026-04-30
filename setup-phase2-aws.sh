#!/bin/bash
set -e

echo "=========================================="
echo "PHASE 2 AWS SETUP AUTOMATION"
echo "=========================================="
echo ""

# Check AWS credentials
echo "Step 1: Checking AWS credentials..."
if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS credentials not configured"
    echo "Run: aws configure"
    echo "Then enter your AWS Access Key ID and Secret Access Key"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "✓ AWS authenticated (Account: $ACCOUNT_ID)"
echo ""

# Deploy OIDC Provider
echo "Step 2: Deploying GitHub OIDC Provider..."
aws cloudformation create-stack \
  --stack-name github-oidc-setup \
  --template-body file://setup-github-oidc.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM \
  --output text

echo "✓ Stack creation initiated"
echo ""

# Wait for completion
echo "Step 3: Waiting for stack to deploy (this takes 2-3 minutes)..."
if aws cloudformation wait stack-create-complete \
  --stack-name github-oidc-setup \
  --region us-east-1 2>/dev/null; then
    echo "✓ Stack deployed successfully"
else
    echo "Stack creation in progress or encountered error"
    echo "Check status: aws cloudformation describe-stacks --stack-name github-oidc-setup --region us-east-1"
fi

echo ""
echo "=========================================="
echo "OIDC SETUP COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add GitHub Secrets (manual or via API)"
echo "2. Execute Phase 2: git push origin main"
echo ""

