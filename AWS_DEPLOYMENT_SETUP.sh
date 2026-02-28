#!/bin/bash
# AWS Deployment Setup Script for Lambda + RDS
# This script prepares your AWS environment for production deployment
# Run this BEFORE deploying Lambda

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    AWS DEPLOYMENT SETUP - Stock Analysis API                  ║"
echo "║    This script configures RDS + Secrets Manager + Lambda      ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
DB_HOST=${DB_HOST:-}
DB_USER=${DB_USER:-stocks}
DB_PASSWORD=${DB_PASSWORD:-bed0elAn}
DB_NAME=${DB_NAME:-stocks}
SECURITY_GROUP_ID=${SECURITY_GROUP_ID:-}
SUBNET_ID_1=${SUBNET_ID_1:-}
SUBNET_ID_2=${SUBNET_ID_2:-}

echo "📋 Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  DB User: $DB_USER"
echo "  DB Name: $DB_NAME"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI and configure credentials."
    exit 1
fi

echo "✅ AWS CLI found"
echo ""

# Step 1: Get RDS Details
if [ -z "$DB_HOST" ]; then
    echo "⚠️  DB_HOST not set. Please provide RDS endpoint:"
    echo "   Run: aws rds describe-db-instances --region $AWS_REGION"
    echo "   Find: Endpoint (e.g., stocks-db.xxxx.us-east-1.rds.amazonaws.com)"
    read -p "Enter RDS Endpoint: " DB_HOST
fi

if [ -z "$DB_HOST" ]; then
    echo "❌ RDS endpoint required. Exiting."
    exit 1
fi

echo "✅ Using RDS endpoint: $DB_HOST"
echo ""

# Step 2: Create Secrets Manager Secret
echo "🔐 Creating AWS Secrets Manager secret..."

SECRET_JSON="{
  \"username\": \"$DB_USER\",
  \"password\": \"$DB_PASSWORD\",
  \"host\": \"$DB_HOST\",
  \"port\": 5432,
  \"dbname\": \"$DB_NAME\"
}"

SECRET_ARN=$(aws secretsmanager create-secret \
  --name stocks/rds/credentials \
  --description "PostgreSQL RDS credentials for Stock Analysis API" \
  --secret-string "$SECRET_JSON" \
  --region $AWS_REGION \
  --query 'ARN' \
  --output text 2>/dev/null || \
aws secretsmanager update-secret \
  --secret-id stocks/rds/credentials \
  --secret-string "$SECRET_JSON" \
  --region $AWS_REGION \
  --query 'ARN' \
  --output text)

echo "✅ Secret created/updated: $SECRET_ARN"
echo ""

# Step 3: Get VPC Details
if [ -z "$SECURITY_GROUP_ID" ] || [ -z "$SUBNET_ID_1" ]; then
    echo "🔍 Fetching VPC details..."

    VPCS=$(aws ec2 describe-vpcs --region $AWS_REGION --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' --output text)

    if [ -z "$SECURITY_GROUP_ID" ]; then
        echo ""
        echo "🛡️  Available Security Groups:"
        aws ec2 describe-security-groups \
          --region $AWS_REGION \
          --query 'SecurityGroups[*].[GroupId,GroupName,VpcId]' \
          --output table

        read -p "Enter Security Group ID (e.g., sg-xxxxx): " SECURITY_GROUP_ID
    fi

    if [ -z "$SUBNET_ID_1" ]; then
        echo ""
        echo "🌐 Available Subnets:"
        aws ec2 describe-subnets \
          --region $AWS_REGION \
          --query 'Subnets[*].[SubnetId,AvailabilityZone,CidrBlock]' \
          --output table

        read -p "Enter Subnet ID 1 (private subnet, e.g., subnet-xxxxx): " SUBNET_ID_1
        read -p "Enter Subnet ID 2 (private subnet, e.g., subnet-xxxxx): " SUBNET_ID_2
    fi
fi

echo "✅ VPC Configuration:"
echo "   Security Group: $SECURITY_GROUP_ID"
echo "   Subnet 1: $SUBNET_ID_1"
echo "   Subnet 2: $SUBNET_ID_2"
echo ""

# Step 4: Save Configuration
echo "💾 Saving configuration to .env.production..."

cat > /home/arger/algo/webapp/lambda/.env.production << EOF
# AWS Production Configuration
# Generated: $(date)

# Secrets Manager
DB_SECRET_ARN=$SECRET_ARN

# AWS Lambda VPC Configuration
AWS_SECURITY_GROUP_ID=$SECURITY_GROUP_ID
AWS_SUBNET_ID_1=$SUBNET_ID_1
AWS_SUBNET_ID_2=$SUBNET_ID_2

# AWS Region
AWS_REGION=$AWS_REGION
WEBAPP_AWS_REGION=$AWS_REGION

# Lambda Runtime
NODE_ENV=production
AWS_LAMBDA_FUNCTION_NAME=stocks-algo-api-dev-api

# Email Configuration
CONTACT_NOTIFICATION_EMAIL=edgebrookecapital@gmail.com
EMAIL_FROM=noreply@bullseyefinancial.com
EOF

echo "✅ Configuration saved to .env.production"
echo ""

# Step 5: Export for Serverless Deploy
echo "📤 Environment variables for deployment:"
echo ""
echo "export DB_SECRET_ARN=$SECRET_ARN"
echo "export AWS_SECURITY_GROUP_ID=$SECURITY_GROUP_ID"
echo "export AWS_SUBNET_ID_1=$SUBNET_ID_1"
echo "export AWS_SUBNET_ID_2=$SUBNET_ID_2"
echo ""

# Step 6: Display Next Steps
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    ✅ SETUP COMPLETE - Ready for Deployment                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1️⃣  Copy the environment variables above and export them:"
echo "   export DB_SECRET_ARN=$SECRET_ARN"
echo "   export AWS_SECURITY_GROUP_ID=$SECURITY_GROUP_ID"
echo "   export AWS_SUBNET_ID_1=$SUBNET_ID_1"
echo "   export AWS_SUBNET_ID_2=$SUBNET_ID_2"
echo ""
echo "2️⃣  Deploy Lambda function:"
echo "   cd webapp/lambda"
echo "   serverless deploy --stage dev --region $AWS_REGION"
echo ""
echo "3️⃣  Test the API:"
echo "   aws lambda invoke --function-name stocks-algo-api-dev-api /tmp/response.json"
echo "   cat /tmp/response.json"
echo ""
echo "4️⃣  Monitor CloudWatch logs:"
echo "   aws logs tail /aws/lambda/stocks-algo-api-dev-api --follow --region $AWS_REGION"
echo ""
echo "📝 Configuration saved to: .env.production"
echo "🔐 Secrets Manager ARN: $SECRET_ARN"
echo ""
