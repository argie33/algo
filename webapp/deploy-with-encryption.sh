#!/bin/bash

# Financial Dashboard API - Lambda Deployment Script with Encryption Secret
# This script deploys the Lambda function with all required environment variables

set -e

# Configuration
STACK_NAME="financial-dashboard-api"
TEMPLATE_FILE="template-webapp-lambda.yml"
REGION="us-east-1"
ENVIRONMENT="dev"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting Financial Dashboard API deployment...${NC}"

# Check if required parameters are set
if [ -z "$DATABASE_SECRET_ARN" ]; then
    echo -e "${RED}❌ ERROR: DATABASE_SECRET_ARN environment variable is required${NC}"
    exit 1
fi

if [ -z "$DATABASE_ENDPOINT" ]; then
    echo -e "${RED}❌ ERROR: DATABASE_ENDPOINT environment variable is required${NC}"
    exit 1
fi

if [ -z "$COGNITO_USER_POOL_ID" ]; then
    echo -e "${RED}❌ ERROR: COGNITO_USER_POOL_ID environment variable is required${NC}"
    exit 1
fi

if [ -z "$COGNITO_CLIENT_ID" ]; then
    echo -e "${RED}❌ ERROR: COGNITO_CLIENT_ID environment variable is required${NC}"
    exit 1
fi

# Generate or use existing API key encryption secret
if [ -z "$API_KEY_ENCRYPTION_SECRET" ]; then
    echo -e "${YELLOW}⚠️  No API_KEY_ENCRYPTION_SECRET provided, generating new one...${NC}"
    API_KEY_ENCRYPTION_SECRET=$(openssl rand -base64 32)
    echo -e "${GREEN}✅ Generated new encryption secret${NC}"
    echo -e "${YELLOW}⚠️  IMPORTANT: Save this encryption secret securely: ${API_KEY_ENCRYPTION_SECRET}${NC}"
else
    echo -e "${GREEN}✅ Using provided API_KEY_ENCRYPTION_SECRET${NC}"
fi

# Create lambda deployment package
echo -e "${GREEN}📦 Creating Lambda deployment package...${NC}"
cd lambda
zip -r ../lambda-package.zip . -x "*.git*" "*.DS_Store*" "**/node_modules/.cache/*"
cd ..

# Deploy the CloudFormation stack
echo -e "${GREEN}🚀 Deploying CloudFormation stack...${NC}"
aws cloudformation deploy \
    --template-file "$TEMPLATE_FILE" \
    --stack-name "$STACK_NAME" \
    --parameter-overrides \
        EnvironmentName="$ENVIRONMENT" \
        DatabaseSecretArn="$DATABASE_SECRET_ARN" \
        DatabaseEndpoint="$DATABASE_ENDPOINT" \
        CognitoUserPoolId="$COGNITO_USER_POOL_ID" \
        CognitoClientId="$COGNITO_CLIENT_ID" \
        ApiKeyEncryptionSecret="$API_KEY_ENCRYPTION_SECRET" \
    --capabilities CAPABILITY_IAM \
    --region "$REGION"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
    
    # Get the API Gateway URL
    API_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='ApiGatewayUrl'].OutputValue" \
        --output text)
    
    echo -e "${GREEN}🌐 API Gateway URL: $API_URL${NC}"
    echo -e "${GREEN}🔧 Test the API: curl $API_URL/health${NC}"
    echo -e "${GREEN}🔐 Test settings: curl $API_URL/settings/api-keys${NC}"
    
else
    echo -e "${RED}❌ Deployment failed!${NC}"
    exit 1
fi