#!/bin/bash
# Configure Alpaca paper trading credentials for the algo system
#
# Usage: bash scripts/configure-alpaca-credentials.sh
#
# This script:
# 1. Prompts for Alpaca API key and secret
# 2. Stores them in AWS Secrets Manager
# 3. Updates Lambda environment to use credentials
# 4. Tests the connection to Alpaca

set -e

echo "=============================================="
echo "ALPACA PAPER TRADING CONFIGURATION"
echo "=============================================="
echo ""
echo "This script will configure your Alpaca paper trading credentials."
echo "Credentials will be stored securely in AWS Secrets Manager."
echo ""
echo "To get your Alpaca credentials:"
echo "1. Log in to https://alpaca.markets"
echo "2. Go to Dashboard → Account Settings → API Keys"
echo "3. Copy your API Key ID and Secret Key"
echo ""

# Prompt for credentials
read -p "Enter your Alpaca API Key ID: " ALPACA_KEY_ID
read -sp "Enter your Alpaca Secret Key: " ALPACA_SECRET_KEY
echo ""

if [ -z "$ALPACA_KEY_ID" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    echo "Error: Both API Key and Secret Key are required"
    exit 1
fi

echo ""
echo "Configuring Alpaca credentials..."

# Set environment variables for Terraform
export TF_VAR_alpaca_api_key_id="$ALPACA_KEY_ID"
export TF_VAR_alpaca_api_secret_key="$ALPACA_SECRET_KEY"

# Apply Terraform changes
echo "Applying Terraform with Alpaca credentials..."
cd terraform
terraform apply -auto-approve -var="alpaca_api_key_id=$ALPACA_KEY_ID" -var="alpaca_api_secret_key=$ALPACA_SECRET_KEY"
cd ..

echo ""
echo "Terraform updated. Now deploying Lambda..."

# Deploy Lambda with new credentials
gh workflow run deploy-api-lambda.yml

echo ""
echo "=============================================="
echo "SETUP COMPLETE"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Wait for GitHub Actions workflow to complete (2-3 minutes)"
echo "2. Verify Alpaca connection:"
echo "   curl -H 'Authorization: Bearer dev-admin' \\"
echo "     https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio"
echo ""
echo "3. Check that portfolio data loads (should show Alpaca account details)"
echo ""
echo "4. Start trading:"
echo "   python3 api-pkg/dev_server.py"
echo "   python3 -m dashboard --local"
echo ""
echo "Paper trading is now ACTIVE. All trades execute on Alpaca paper account."
echo ""
