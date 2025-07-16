#!/bin/bash
# Deploy Alpaca WebSocket Lambda Function
# HFT-ready real-time market data connector deployment

set -e

# Configuration
LAMBDA_NAME="alpaca-websocket-connector"
LAMBDA_RUNTIME="python3.9"
LAMBDA_HANDLER="alpaca-data-connector.lambda_handler"
LAMBDA_TIMEOUT=900  # 15 minutes for long-running WebSocket connections
LAMBDA_MEMORY=1024  # 1GB for high-frequency data processing
LAMBDA_ARCH="x86_64"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying Alpaca WebSocket Lambda Function...${NC}"

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    exit 1
fi

# Check if we're in the right directory
if [ ! -f "alpaca-data-connector.py" ]; then
    echo -e "${RED}❌ alpaca-data-connector.py not found. Run this script from the lambda directory.${NC}"
    exit 1
fi

# Create deployment package
echo -e "${YELLOW}📦 Creating deployment package...${NC}"

# Create a temporary directory for packaging
TEMP_DIR=$(mktemp -d)
echo "Using temp directory: $TEMP_DIR"

# Copy Lambda function
cp alpaca-data-connector.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"

# Install dependencies
echo -e "${YELLOW}📥 Installing dependencies...${NC}"
cd "$TEMP_DIR"

# Install Python dependencies
pip install -r requirements.txt -t .

# Remove unnecessary files to reduce package size
echo -e "${YELLOW}🧹 Cleaning up package...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

# Remove large unnecessary packages
rm -rf boto3* botocore* 2>/dev/null || true  # These are provided by Lambda runtime
rm -rf pandas/tests* 2>/dev/null || true
rm -rf numpy/tests* 2>/dev/null || true

# Create ZIP package
echo -e "${YELLOW}📦 Creating ZIP package...${NC}"
zip -r lambda-deployment.zip . -x "*.git*" "*.DS_Store*" "*/tests/*" "*/test_*" > /dev/null

# Check package size
PACKAGE_SIZE=$(stat -c%s lambda-deployment.zip)
PACKAGE_SIZE_MB=$((PACKAGE_SIZE / 1024 / 1024))
echo "Package size: ${PACKAGE_SIZE_MB}MB"

if [ $PACKAGE_SIZE_MB -gt 50 ]; then
    echo -e "${YELLOW}⚠️  Package size is ${PACKAGE_SIZE_MB}MB. Consider optimizing for faster deployments.${NC}"
fi

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)

if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
    echo -e "${YELLOW}⚠️  No region configured, using default: $AWS_REGION${NC}"
fi

echo "AWS Account ID: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"

# Check if Lambda function exists
if aws lambda get-function --function-name "$LAMBDA_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo -e "${YELLOW}🔄 Updating existing Lambda function...${NC}"
    
    # Update function code
    aws lambda update-function-code \
        --function-name "$LAMBDA_NAME" \
        --zip-file fileb://lambda-deployment.zip \
        --region "$AWS_REGION" \
        --output table
    
    # Update function configuration
    aws lambda update-function-configuration \
        --function-name "$LAMBDA_NAME" \
        --timeout "$LAMBDA_TIMEOUT" \
        --memory-size "$LAMBDA_MEMORY" \
        --region "$AWS_REGION" \
        --output table
    
    echo -e "${GREEN}✅ Lambda function updated successfully!${NC}"
else
    echo -e "${YELLOW}📝 Creating new Lambda function...${NC}"
    
    # Create execution role ARN
    ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/AlpacaWebSocketRole"
    
    # Create Lambda function
    aws lambda create-function \
        --function-name "$LAMBDA_NAME" \
        --runtime "$LAMBDA_RUNTIME" \
        --role "$ROLE_ARN" \
        --handler "$LAMBDA_HANDLER" \
        --zip-file fileb://lambda-deployment.zip \
        --timeout "$LAMBDA_TIMEOUT" \
        --memory-size "$LAMBDA_MEMORY" \
        --architectures "$LAMBDA_ARCH" \
        --region "$AWS_REGION" \
        --description "Alpaca WebSocket data connector for HFT" \
        --output table
    
    echo -e "${GREEN}✅ Lambda function created successfully!${NC}"
fi

# Set environment variables (these would be set by CloudFormation in real deployment)
echo -e "${YELLOW}🔧 Setting environment variables...${NC}"
aws lambda update-function-configuration \
    --function-name "$LAMBDA_NAME" \
    --environment "Variables={
        CONNECTIONS_TABLE_NAME=alpaca-connections,
        SUBSCRIPTIONS_TABLE_NAME=alpaca-subscriptions,
        MARKET_DATA_TABLE_NAME=alpaca-market-data,
        ALPACA_CREDENTIALS_SECRET=alpaca-credentials,
        WEBSOCKET_ENDPOINT=https://your-websocket-api.execute-api.${AWS_REGION}.amazonaws.com/dev
    }" \
    --region "$AWS_REGION" \
    --output table

# Clean up
cd - > /dev/null
rm -rf "$TEMP_DIR"

echo -e "${GREEN}🎉 Deployment complete!${NC}"
echo -e "${GREEN}Function name: $LAMBDA_NAME${NC}"
echo -e "${GREEN}Region: $AWS_REGION${NC}"
echo -e "${GREEN}Package size: ${PACKAGE_SIZE_MB}MB${NC}"

# Get function info
echo -e "${YELLOW}📊 Function information:${NC}"
aws lambda get-function \
    --function-name "$LAMBDA_NAME" \
    --region "$AWS_REGION" \
    --query 'Configuration.[FunctionName,Runtime,Handler,Timeout,MemorySize,LastModified]' \
    --output table

echo -e "${GREEN}✅ Alpaca WebSocket Lambda deployment complete!${NC}"
echo -e "${YELLOW}💡 Remember to update the CloudFormation template with the correct Lambda function ARN${NC}"