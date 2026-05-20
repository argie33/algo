#!/bin/bash
# DEPLOY TO AWS - Step by Step
# This script automates AWS deployment. Run this to get the system live.

set -e

echo "=========================================="
echo "DEPLOYING TO AWS"
echo "=========================================="
echo ""

# Step 1: Verify credentials
echo "STEP 1: Verifying credentials..."
echo ""
echo "Checking Alpaca credentials..."
if [ -z "$APCA_API_KEY_ID" ]; then
    echo "❌ APCA_API_KEY_ID not set"
    echo "   You must have this in PowerShell profile or environment"
    exit 1
fi
echo "✅ Alpaca Key ID found"

echo ""
echo "Checking FRED credentials..."
if [ -z "$FRED_API_KEY" ]; then
    echo "❌ FRED_API_KEY not set"
    exit 1
fi
echo "✅ FRED API Key found"

echo ""
echo "Checking RDS credentials..."
if [ -z "$RDS_PASSWORD" ]; then
    echo "❌ RDS_PASSWORD not set"
    echo ""
    echo "   OPTIONS TO GET RDS PASSWORD:"
    echo ""
    echo "   OPTION A: AWS Console"
    echo "   1. Go to https://console.aws.amazon.com/"
    echo "   2. RDS → Databases → find 'stocks-prod' (or similar)"
    echo "   3. Click on it → scroll to 'Master username' section"
    echo "   4. Note: you set this password when creating the database"
    echo "   5. If forgotten, you can modify the database to reset it"
    echo ""
    echo "   OPTION B: Check your local notes/password manager"
    echo "   (What did you set when creating the RDS instance?)"
    echo ""
    echo "   Once you have the password, run:"
    echo "   export RDS_PASSWORD='your_actual_password'"
    echo "   ./DEPLOY_TO_AWS.sh"
    exit 1
fi
echo "✅ RDS Password found"

echo ""
echo "=========================================="
echo "STEP 2: Creating AWS Secrets Manager entries..."
echo "=========================================="
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found"
    echo "   Install it: https://aws.amazon.com/cli/"
    echo "   Or run: pip install awscli"
    exit 1
fi

# Check if AWS is configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "⚠️  AWS credentials not configured"
    echo "   Run: aws configure"
    echo "   You need: AWS Access Key ID, Secret Access Key, region (us-east-1), output (json)"
    exit 1
fi

echo "✅ AWS CLI configured"
echo ""

# Create Alpaca secret
echo "Creating algo/alpaca secret..."
aws secretsmanager create-secret \
    --name algo/alpaca \
    --secret-string "{\"api_key\":\"$APCA_API_KEY_ID\",\"api_secret\":\"$APCA_API_SECRET_KEY\"}" \
    --region us-east-1 \
    --tags Key=Project,Value=algo \
    2>/dev/null || aws secretsmanager update-secret \
    --secret-id algo/alpaca \
    --secret-string "{\"api_key\":\"$APCA_API_KEY_ID\",\"api_secret\":\"$APCA_API_SECRET_KEY\"}" \
    --region us-east-1
echo "✅ Alpaca secret created/updated"

# Create FRED secret
echo "Creating algo/fred secret..."
aws secretsmanager create-secret \
    --name algo/fred \
    --secret-string "{\"api_key\":\"$FRED_API_KEY\"}" \
    --region us-east-1 \
    --tags Key=Project,Value=algo \
    2>/dev/null || aws secretsmanager update-secret \
    --secret-id algo/fred \
    --secret-string "{\"api_key\":\"$FRED_API_KEY\"}" \
    --region us-east-1
echo "✅ FRED secret created/updated"

# Create Database secret
echo "Creating algo/database secret..."
# Get RDS endpoint (assuming it follows naming pattern)
RDS_HOST="${RDS_HOST:-stocks-prod.c9akciq32.us-east-1.rds.amazonaws.com}"
aws secretsmanager create-secret \
    --name algo/database \
    --secret-string "{\"host\":\"$RDS_HOST\",\"user\":\"stocks\",\"password\":\"$RDS_PASSWORD\",\"port\":5432,\"database\":\"stocks\"}" \
    --region us-east-1 \
    --tags Key=Project,Value=algo \
    2>/dev/null || aws secretsmanager update-secret \
    --secret-id algo/database \
    --secret-string "{\"host\":\"$RDS_HOST\",\"user\":\"stocks\",\"password\":\"$RDS_PASSWORD\",\"port\":5432,\"database\":\"stocks\"}" \
    --region us-east-1
echo "✅ Database secret created/updated"

echo ""
echo "=========================================="
echo "STEP 3: Deploying to AWS via GitHub Actions..."
echo "=========================================="
echo ""

# Push to GitHub
git add -A
git commit -m "deploy: AWS secrets configured, ready for live trading in AWS" || echo "No changes to commit"
git push origin main

echo ""
echo "✅ Code pushed to GitHub"
echo ""
echo "Monitor deployment at:"
echo "  https://github.com/argie33/algo/actions"
echo ""
echo "GitHub Actions will:"
echo "  1. Run security scans"
echo "  2. Run tests"
echo "  3. Deploy Terraform (VPC, RDS, Lambda, EventBridge)"
echo "  4. Deploy Lambda functions"
echo "  5. Configure EventBridge schedules"
echo ""
echo "Deployment will take 10-15 minutes"
echo ""
echo "Once complete:"
echo "  - Loaders will run at 4:00 AM ET daily"
echo "  - Orchestrator will run at 9:30 AM ET and 5:30 PM ET"
echo "  - Real trades will execute in Alpaca paper account"
echo ""
echo "=========================================="
echo "✅ DEPLOYMENT INITIATED"
echo "=========================================="
