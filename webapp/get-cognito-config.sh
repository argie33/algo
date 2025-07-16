#!/bin/bash

# Script to retrieve AWS Cognito configuration from CloudFormation stack
# Usage: ./get-cognito-config.sh [environment]

set -e

ENVIRONMENT=${1:-prod}
STACK_NAME="stocks-serverless-webapp"
AWS_REGION="us-east-1"

echo "🔍 Retrieving Cognito configuration from AWS CloudFormation..."
echo "Stack: $STACK_NAME"
echo "Region: $AWS_REGION"
echo ""

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed."
    echo "Please install AWS CLI and configure your credentials."
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials are not configured."
    echo "Please run 'aws configure' to set up your credentials."
    exit 1
fi

echo "✅ AWS CLI configured and authenticated"
echo ""

# Get stack outputs
echo "📋 Retrieving stack outputs..."

API_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")

CLIENT_ID=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")

COGNITO_DOMAIN=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`UserPoolDomain`].OutputValue' \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")

CLOUDFRONT_URL=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`SPAUrl`].OutputValue' \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    echo "❌ Unable to retrieve Cognito configuration from stack."
    echo "Please ensure the CloudFormation stack '$STACK_NAME' is deployed correctly."
    exit 1
fi

echo "✅ Successfully retrieved Cognito configuration:"
echo ""
echo "🔧 Configuration Values:"
echo "  API_URL: $API_URL"
echo "  USER_POOL_ID: $USER_POOL_ID"
echo "  CLIENT_ID: $CLIENT_ID"
echo "  COGNITO_DOMAIN: $COGNITO_DOMAIN"
echo "  CLOUDFRONT_URL: $CLOUDFRONT_URL"
echo ""

# Update frontend environment files
echo "📝 Updating frontend environment files..."

cd frontend

# Update .env.production
cat > .env.production << EOF
# Production Environment - Auto-generated
VITE_API_URL=$API_URL
VITE_SERVERLESS=true
VITE_ENVIRONMENT=production

# AWS Cognito Configuration
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
VITE_AWS_REGION=$AWS_REGION
VITE_COGNITO_DOMAIN=$COGNITO_DOMAIN
VITE_COGNITO_REDIRECT_SIGN_IN=https://$CLOUDFRONT_URL
VITE_COGNITO_REDIRECT_SIGN_OUT=https://$CLOUDFRONT_URL
EOF

# Update .env.development with real values for testing
cat > .env.development << EOF
# Development Environment
VITE_API_URL=$API_URL
VITE_SERVERLESS=true
VITE_ENVIRONMENT=dev

# AWS Cognito Configuration - Real values for testing
VITE_COGNITO_USER_POOL_ID=$USER_POOL_ID
VITE_COGNITO_CLIENT_ID=$CLIENT_ID
VITE_AWS_REGION=$AWS_REGION
VITE_COGNITO_DOMAIN=$COGNITO_DOMAIN
VITE_COGNITO_REDIRECT_SIGN_IN=http://localhost:3000
VITE_COGNITO_REDIRECT_SIGN_OUT=http://localhost:3000
EOF

cd ..

# Update lambda environment
echo "📝 Updating lambda environment file..."

cd lambda

cat > .env << EOF
# Local development environment variables
NODE_ENV=development
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=postgres
DB_PASSWORD=password

# AWS Cognito Configuration - Real values from CloudFormation
COGNITO_USER_POOL_ID=$USER_POOL_ID
COGNITO_CLIENT_ID=$CLIENT_ID
AWS_REGION=$AWS_REGION
WEBAPP_AWS_REGION=$AWS_REGION
EOF

cd ..

echo "✅ Environment files updated successfully!"
echo ""
echo "🚀 Next steps:"
echo "  1. Start backend: cd lambda && npm start"
echo "  2. Start frontend: cd frontend && npm run dev"
echo "  3. Test authentication flow"
echo ""
echo "💡 For production deployment, the CI/CD pipeline will use these values automatically."