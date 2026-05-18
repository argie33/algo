#!/bin/bash
# Setup AWS Secrets Manager for Stock Analytics Platform
# Creates the RDS credentials secret that Lambda will use

set -e

echo "========================================================================"
echo "AWS Secrets Manager Setup"
echo "========================================================================"
echo ""

# Check AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "[ERROR] AWS CLI not found. Install from: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials are configured
if ! aws sts get-caller-identity &> /dev/null; then
    echo "[ERROR] AWS credentials not configured. Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}

echo "[OK] AWS credentials configured"
echo "[INFO] Account: $ACCOUNT_ID"
echo "[INFO] Region: $REGION"
echo ""

# Get RDS endpoint
echo "Enter RDS Database Details:"
echo ""

read -p "RDS Endpoint (your-db.xxxxx.rds.amazonaws.com): " RDS_ENDPOINT
if [ -z "$RDS_ENDPOINT" ]; then
    echo "[ERROR] RDS_ENDPOINT is required"
    exit 1
fi

read -p "Database Port (default 5432): " RDS_PORT
RDS_PORT=${RDS_PORT:-5432}

read -p "Database Username (default stocks): " RDS_USERNAME
RDS_USERNAME=${RDS_USERNAME:-stocks}

read -sp "Database Password: " RDS_PASSWORD
echo ""

if [ -z "$RDS_PASSWORD" ]; then
    echo "[ERROR] Database password is required"
    exit 1
fi

read -p "Database Name (default stocks): " RDS_DATABASE
RDS_DATABASE=${RDS_DATABASE:-stocks}

echo ""
echo "========================================================================"
echo "Creating AWS Secrets Manager Secret"
echo "========================================================================"
echo ""

SECRET_NAME="algo/db/postgres"
SECRET_VALUE="{\"host\":\"$RDS_ENDPOINT\",\"port\":$RDS_PORT,\"username\":\"$RDS_USERNAME\",\"password\":\"$RDS_PASSWORD\",\"dbname\":\"$RDS_DATABASE\"}"

echo "[INFO] Secret Name: $SECRET_NAME"
echo "[INFO] Host: $RDS_ENDPOINT"
echo "[INFO] Port: $RDS_PORT"
echo "[INFO] Username: $RDS_USERNAME"
echo "[INFO] Database: $RDS_DATABASE"
echo ""

# Check if secret already exists
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" &> /dev/null; then
    echo "[INFO] Secret already exists. Updating..."
    aws secretsmanager update-secret \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --region "$REGION"
    echo "[OK] Secret updated"
else
    echo "[INFO] Creating new secret..."
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --secret-string "$SECRET_VALUE" \
        --region "$REGION"
    echo "[OK] Secret created"
fi

echo ""
echo "========================================================================"
echo "Getting Secret ARN"
echo "========================================================================"
echo ""

SECRET_ARN=$(aws secretsmanager describe-secret \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query 'ARN' \
    --output text)

echo "[OK] Secret ARN: $SECRET_ARN"
echo ""
echo "COPY THIS AND SET IN GITHUB SECRET: DB_SECRET_ARN"
echo ""

# Verify secret is accessible
echo "========================================================================"
echo "Verifying Secret Access"
echo "========================================================================"
echo ""

echo "[INFO] Testing secret retrieval..."
aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query 'SecretString' \
    --output text | jq .

echo ""
echo "[OK] Secret created and verified successfully!"
echo ""
echo "Next Step: Add this ARN to GitHub Secret DB_SECRET_ARN"
echo "  $SECRET_ARN"
