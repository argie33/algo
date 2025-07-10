#!/bin/bash

# Deploy Lambda Fix Script
# This script packages and updates the Lambda function with the fixed code

echo "🔧 Lambda Deployment Fix Script"
echo "==============================="

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Get function name from environment or use default
FUNCTION_NAME="${1:-financial-dashboard-api-dev}"
echo "📋 Function Name: $FUNCTION_NAME"

# Clean up any existing deployment files
echo "🧹 Cleaning up old deployment files..."
rm -f function.zip
rm -f lambda-package.zip

# Create deployment package
echo "📦 Creating deployment package..."
zip -r function.zip . \
    -x "*.git*" \
    -x "*.DS_Store" \
    -x "test*" \
    -x "*.log" \
    -x "deploy-fix.sh" \
    -x "README*" \
    -x "*.md"

# Check if zip was created successfully
if [ ! -f "function.zip" ]; then
    echo "❌ Failed to create deployment package"
    exit 1
fi

echo "📏 Package size: $(du -h function.zip | cut -f1)"

# Update Lambda function code
echo "🚀 Updating Lambda function code..."
aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file fileb://function.zip \
    --region us-east-1

if [ $? -eq 0 ]; then
    echo "✅ Lambda function updated successfully"
    
    # Wait for update to complete
    echo "⏳ Waiting for function update to complete..."
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region us-east-1
    
    echo "🧪 Testing function after update..."
    # Test the function
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"httpMethod":"GET","path":"/health","queryStringParameters":{"quick":"true"}}' \
        --region us-east-1 \
        response.json
    
    echo "📋 Test response:"
    cat response.json
    echo
    
    # Clean up
    rm -f function.zip response.json
    
    echo "✅ Deployment complete!"
    echo "🔗 Test URL: https://q570hqc8i9.execute-api.us-east-1.amazonaws.com/dev/health?quick=true"
else
    echo "❌ Lambda function update failed"
    rm -f function.zip
    exit 1
fi