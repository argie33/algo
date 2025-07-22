#!/bin/bash
# Setup AWS Secrets Manager for Full Integration Testing

set -e

REGION="us-east-1"
ENVIRONMENT="dev"

echo "🔐 Setting up AWS Secrets Manager for integration testing..."

# 1. API Key Encryption Secret
echo "Creating API key encryption secret..."
aws secretsmanager create-secret \
    --region $REGION \
    --name "api-key-encryption-$ENVIRONMENT" \
    --description "Encryption key for API key storage" \
    --secret-string "{\"key\":\"$(openssl rand -base64 32)\"}" \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Secret api-key-encryption-$ENVIRONMENT may already exist"

# 2. JWT Secret Key
echo "Creating JWT secret key..."
aws secretsmanager create-secret \
    --region $REGION \
    --name "jwt-secret-key-$ENVIRONMENT" \
    --description "JWT signing secret for authentication" \
    --secret-string "{\"secret\":\"$(openssl rand -base64 64)\"}" \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Secret jwt-secret-key-$ENVIRONMENT may already exist"

# 3. Alpaca API Credentials (placeholder)
echo "Creating Alpaca API credentials secret..."
aws secretsmanager create-secret \
    --region $REGION \
    --name "alpaca-api-credentials-$ENVIRONMENT" \
    --description "Alpaca trading API credentials" \
    --secret-string "{\"api_key\":\"PLACEHOLDER_KEY\",\"secret_key\":\"PLACEHOLDER_SECRET\",\"paper_trading\":true}" \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Secret alpaca-api-credentials-$ENVIRONMENT may already exist"

# 4. External API Keys
echo "Creating external API keys secret..."
aws secretsmanager create-secret \
    --region $REGION \
    --name "external-api-keys-$ENVIRONMENT" \
    --description "External API service keys" \
    --secret-string "{
        \"huggingface_api_key\":\"PLACEHOLDER_HF_KEY\",
        \"finnhub_api_key\":\"PLACEHOLDER_FINNHUB_KEY\",
        \"alpha_vantage_api_key\":\"PLACEHOLDER_AV_KEY\"
    }" \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Secret external-api-keys-$ENVIRONMENT may already exist"

# 5. Session Encryption Keys
echo "Creating session encryption secret..."
aws secretsmanager create-secret \
    --region $REGION \
    --name "session-encryption-$ENVIRONMENT" \
    --description "Session encryption keys" \
    --secret-string "{
        \"session_secret\":\"$(openssl rand -base64 32)\",
        \"cookie_secret\":\"$(openssl rand -base64 24)\"
    }" \
    --tags Key="Environment",Value="$ENVIRONMENT" Key="Service",Value="stocks-webapp" \
    || echo "Secret session-encryption-$ENVIRONMENT may already exist"

echo "✅ AWS Secrets Manager setup complete!"
echo ""
echo "📝 Update your environment variables:"
echo "export API_KEY_ENCRYPTION_SECRET_ARN=\"arn:aws:secretsmanager:$REGION:$(aws sts get-caller-identity --query Account --output text):secret:api-key-encryption-$ENVIRONMENT\""
echo "export JWT_SECRET_ARN=\"arn:aws:secretsmanager:$REGION:$(aws sts get-caller-identity --query Account --output text):secret:jwt-secret-key-$ENVIRONMENT\""
echo "export ALPACA_SECRET_ARN=\"arn:aws:secretsmanager:$REGION:$(aws sts get-caller-identity --query Account --output text):secret:alpaca-api-credentials-$ENVIRONMENT\""
echo "export EXTERNAL_API_KEYS_ARN=\"arn:aws:secretsmanager:$REGION:$(aws sts get-caller-identity --query Account --output text):secret:external-api-keys-$ENVIRONMENT\""