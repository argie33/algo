#!/bin/bash

# Fix Lambda Environment Variables Script
# This script updates the Lambda function with the missing API_KEY_ENCRYPTION_SECRET

echo "🔧 Lambda Environment Variables Fix"
echo "===================================="

# Get function name from environment or use default
FUNCTION_NAME="${1:-financial-dashboard-api-dev}"
echo "📋 Function Name: $FUNCTION_NAME"

# Generate a secure encryption secret
echo "🔐 Generating secure API key encryption secret..."
API_KEY_ENCRYPTION_SECRET=$(openssl rand -base64 32)
echo "✅ Generated encryption secret: ${API_KEY_ENCRYPTION_SECRET:0:8}..."

# Get current environment variables
echo "🔍 Getting current environment variables..."
CURRENT_ENV=$(aws lambda get-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --region us-east-1 \
    --query 'Environment.Variables' \
    --output json)

if [ $? -ne 0 ]; then
    echo "❌ Failed to get current environment variables"
    exit 1
fi

echo "📋 Current environment variables:"
echo "$CURRENT_ENV" | jq -r 'keys[]'

# Update environment variables with the encryption secret
echo "🔄 Updating environment variables..."
aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables=$(echo "$CURRENT_ENV" | jq --arg secret "$API_KEY_ENCRYPTION_SECRET" '. + {API_KEY_ENCRYPTION_SECRET: $secret}')" \
    --region us-east-1

if [ $? -eq 0 ]; then
    echo "✅ Environment variables updated successfully"
    
    # Wait for update to complete
    echo "⏳ Waiting for environment update to complete..."
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region us-east-1
    
    echo "🧪 Testing settings endpoint after update..."
    # Test the settings endpoint
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"httpMethod":"GET","path":"/settings/api-keys","headers":{"authorization":"Bearer dummy-token"}}' \
        --region us-east-1 \
        response.json
    
    echo "📋 Settings test response:"
    cat response.json | jq .
    echo
    
    # Test that the module now loads
    echo "🔍 Testing module loading..."
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"httpMethod":"GET","path":"/health","queryStringParameters":{"quick":"true"}}' \
        --region us-east-1 \
        health-response.json
    
    echo "📋 Health check response:"
    cat health-response.json | jq .
    echo
    
    # Clean up
    rm -f response.json health-response.json
    
    echo "✅ Environment variable fix complete!"
    echo "🔐 API_KEY_ENCRYPTION_SECRET has been set"
    echo "⚠️  IMPORTANT: Save this encryption secret securely: $API_KEY_ENCRYPTION_SECRET"
    echo "🔗 Test URL: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/settings/api-keys"
else
    echo "❌ Failed to update environment variables"
    exit 1
fi