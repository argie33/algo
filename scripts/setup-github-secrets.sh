#!/bin/bash
# Setup GitHub Secrets for Stock Analytics Platform
# Run this script to configure all 5 required secrets
# Requires: gh CLI installed and authenticated

set -e

echo "========================================================================"
echo "GitHub Secrets Setup"
echo "========================================================================"
echo ""

# Check gh CLI is available
if ! command -v gh &> /dev/null; then
    echo "[ERROR] gh CLI not found. Install from: https://github.com/cli/cli"
    exit 1
fi

# Verify authenticated
if ! gh auth status &> /dev/null; then
    echo "[ERROR] gh CLI not authenticated. Run: gh auth login"
    exit 1
fi

echo "[OK] gh CLI authenticated"
echo ""

# Get values from user
echo "Enter the following values (or press Enter to skip):"
echo ""

read -p "AWS_ACCOUNT_ID (12-digit number): " AWS_ACCOUNT_ID
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo "[SKIP] AWS_ACCOUNT_ID not provided"
else
    echo "[SET] AWS_ACCOUNT_ID = $AWS_ACCOUNT_ID"
fi

read -p "API_GATEWAY_URL (https://...): " API_GATEWAY_URL
if [ -z "$API_GATEWAY_URL" ]; then
    echo "[SKIP] API_GATEWAY_URL not provided"
else
    echo "[SET] API_GATEWAY_URL = $API_GATEWAY_URL"
fi

read -p "DB_SECRET_ARN (arn:aws:secretsmanager:...): " DB_SECRET_ARN
if [ -z "$DB_SECRET_ARN" ]; then
    echo "[SKIP] DB_SECRET_ARN not provided"
else
    echo "[SET] DB_SECRET_ARN = $DB_SECRET_ARN"
fi

read -p "COGNITO_USER_POOL_ID (us-east-1_...): " COGNITO_USER_POOL_ID
if [ -z "$COGNITO_USER_POOL_ID" ]; then
    echo "[SKIP] COGNITO_USER_POOL_ID not provided"
else
    echo "[SET] COGNITO_USER_POOL_ID = $COGNITO_USER_POOL_ID"
fi

read -p "COGNITO_CLIENT_ID (alphanumeric): " COGNITO_CLIENT_ID
if [ -z "$COGNITO_CLIENT_ID" ]; then
    echo "[SKIP] COGNITO_CLIENT_ID not provided"
else
    echo "[SET] COGNITO_CLIENT_ID = $COGNITO_CLIENT_ID"
fi

echo ""
echo "========================================================================"
echo "Setting GitHub Secrets"
echo "========================================================================"
echo ""

# Set secrets
if [ -n "$AWS_ACCOUNT_ID" ]; then
    echo "[Setting] AWS_ACCOUNT_ID..."
    gh secret set AWS_ACCOUNT_ID --body "$AWS_ACCOUNT_ID"
    echo "[OK] AWS_ACCOUNT_ID set"
fi

if [ -n "$API_GATEWAY_URL" ]; then
    echo "[Setting] API_GATEWAY_URL..."
    gh secret set API_GATEWAY_URL --body "$API_GATEWAY_URL"
    echo "[OK] API_GATEWAY_URL set"
fi

if [ -n "$DB_SECRET_ARN" ]; then
    echo "[Setting] DB_SECRET_ARN..."
    gh secret set DB_SECRET_ARN --body "$DB_SECRET_ARN"
    echo "[OK] DB_SECRET_ARN set"
fi

if [ -n "$COGNITO_USER_POOL_ID" ]; then
    echo "[Setting] COGNITO_USER_POOL_ID..."
    gh secret set COGNITO_USER_POOL_ID --body "$COGNITO_USER_POOL_ID"
    echo "[OK] COGNITO_USER_POOL_ID set"
fi

if [ -n "$COGNITO_CLIENT_ID" ]; then
    echo "[Setting] COGNITO_CLIENT_ID..."
    gh secret set COGNITO_CLIENT_ID --body "$COGNITO_CLIENT_ID"
    echo "[OK] COGNITO_CLIENT_ID set"
fi

echo ""
echo "========================================================================"
echo "Verifying Secrets"
echo "========================================================================"
echo ""

gh secret list

echo ""
echo "[OK] GitHub Secrets configured successfully!"
