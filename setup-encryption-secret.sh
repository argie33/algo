#!/bin/bash

# Setup API Key Encryption Secret in AWS Secrets Manager
# This script creates the required secret for API key encryption in the Lambda functions

echo "🔐 Setting up API Key Encryption Secret in AWS Secrets Manager..."
echo "=================================================="

# Generate a secure 256-bit (32-byte) encryption key
echo "📍 Generating secure 256-bit encryption key..."
ENCRYPTION_KEY=$(openssl rand -hex 32)

if [ -z "$ENCRYPTION_KEY" ]; then
    echo "❌ Failed to generate encryption key"
    exit 1
fi

echo "✅ Generated encryption key: ${ENCRYPTION_KEY:0:8}...${ENCRYPTION_KEY: -8}"

# Create the secret in AWS Secrets Manager
echo "📍 Creating secret in AWS Secrets Manager..."

SECRET_VALUE="{\"API_KEY_ENCRYPTION_SECRET\":\"$ENCRYPTION_KEY\"}"

aws secretsmanager create-secret \
    --name "algo-trade-api-keys" \
    --description "Encryption secret for API key storage in algo trading application" \
    --secret-string "$SECRET_VALUE" \
    --region us-east-1

if [ $? -eq 0 ]; then
    echo "✅ Successfully created secret 'algo-trade-api-keys'"
    echo ""
    echo "📋 Next steps:"
    echo "1. Redeploy your CloudFormation stack to pick up the new secret"
    echo "2. Test the API endpoints to verify they're working"
    echo "3. Run the API key integration tests"
    echo ""
    echo "🚀 Command to redeploy:"
    echo "   .github/workflows/deploy-to-dev.yml (via GitHub Actions)"
    echo "   or manually trigger deployment pipeline"
else
    echo "❌ Failed to create secret. Error details above."
    echo ""
    echo "🔍 Troubleshooting:"
    echo "1. Ensure AWS CLI is configured with proper credentials"
    echo "2. Verify you have secretsmanager:CreateSecret permission"
    echo "3. Check if secret already exists (try updating instead):"
    echo "   aws secretsmanager update-secret --secret-id algo-trade-api-keys --secret-string '$SECRET_VALUE'"
    exit 1
fi

echo ""
echo "🔒 Security Notes:"
echo "- The encryption key is randomly generated and secure"
echo "- Store this script securely - it contains the encryption key"
echo "- The key is now safely stored in AWS Secrets Manager"
echo "- Lambda functions will automatically retrieve it from Secrets Manager"