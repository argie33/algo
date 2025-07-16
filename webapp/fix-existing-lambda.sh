#!/bin/bash

set -e

echo "🔧 Fixing existing Lambda function configuration"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Set AWS region
AWS_REGION=${AWS_REGION:-us-east-1}
export AWS_DEFAULT_REGION=$AWS_REGION

print_status "Using AWS region: $AWS_REGION"

# Step 1: Find the Lambda function
print_status "Finding Lambda function..."

# Try to find Lambda functions that might be the webapp
LAMBDA_FUNCTIONS=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'financial') || contains(FunctionName, 'stocks') || contains(FunctionName, 'webapp')].FunctionName" --output table 2>/dev/null || echo "")

if [ -z "$LAMBDA_FUNCTIONS" ]; then
    print_error "No Lambda functions found. Checking all functions..."
    aws lambda list-functions --query "Functions[].FunctionName" --output table 2>/dev/null || {
        print_error "Cannot list Lambda functions. AWS CLI may not be configured."
        exit 1
    }
    exit 1
fi

print_status "Found potential Lambda functions:"
echo "$LAMBDA_FUNCTIONS"

# Try common function name patterns
FUNCTION_NAMES=("financial-dashboard-api-dev" "financial-dashboard-api-prod" "stocks-webapp-api" "webapp-api" "api-function")

LAMBDA_FUNCTION=""
for func_name in "${FUNCTION_NAMES[@]}"; do
    if aws lambda get-function --function-name "$func_name" >/dev/null 2>&1; then
        LAMBDA_FUNCTION="$func_name"
        break
    fi
done

if [ -z "$LAMBDA_FUNCTION" ]; then
    print_error "Could not find the webapp Lambda function automatically."
    print_status "Please specify the function name manually:"
    echo "Available functions:"
    aws lambda list-functions --query "Functions[].FunctionName" --output table
    exit 1
fi

print_success "Found Lambda function: $LAMBDA_FUNCTION"

# Step 2: Find the database secret
print_status "Finding database secret..."

# Try to find secrets that contain database credentials
SECRET_ARN=$(aws secretsmanager list-secrets \
    --query "SecretList[?contains(Name, 'stocks') && contains(Name, 'db')].ARN | [0]" \
    --output text 2>/dev/null || echo "None")

if [ "$SECRET_ARN" = "None" ] || [ -z "$SECRET_ARN" ]; then
    # Try alternative patterns
    SECRET_ARN=$(aws secretsmanager list-secrets \
        --query "SecretList[?contains(Name, 'rds') || contains(Name, 'database')].ARN | [0]" \
        --output text 2>/dev/null || echo "None")
fi

if [ "$SECRET_ARN" = "None" ] || [ -z "$SECRET_ARN" ]; then
    print_error "Database secret not found. Available secrets:"
    aws secretsmanager list-secrets --query "SecretList[].Name" --output table
    exit 1
fi

print_success "Found database secret: $SECRET_ARN"

# Step 3: Find VPC configuration
print_status "Finding VPC configuration..."

# Get VPC info from existing resources
VPC_ID=$(aws ec2 describe-vpcs --query "Vpcs[?Tags[?Key=='Name' && contains(Value, 'stocks')]].VpcId | [0]" --output text 2>/dev/null || echo "None")

if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    # Try to get the default VPC
    VPC_ID=$(aws ec2 describe-vpcs --query "Vpcs[?IsDefault].VpcId | [0]" --output text 2>/dev/null || echo "None")
fi

if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
    print_error "Could not find VPC. Available VPCs:"
    aws ec2 describe-vpcs --query "Vpcs[].[VpcId,Tags[?Key=='Name'].Value | [0]]" --output table
    exit 1
fi

print_success "Found VPC: $VPC_ID"

# Get public subnets (so Lambda can reach internet)
SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=map-public-ip-on-launch,Values=true" \
    --query "Subnets[].SubnetId" \
    --output text 2>/dev/null || echo "")

if [ -z "$SUBNET_IDS" ]; then
    print_warning "No public subnets found. Trying all subnets..."
    SUBNET_IDS=$(aws ec2 describe-subnets \
        --filters "Name=vpc-id,Values=$VPC_ID" \
        --query "Subnets[0:2].SubnetId" \
        --output text 2>/dev/null || echo "")
fi

if [ -z "$SUBNET_IDS" ]; then
    print_error "Could not find subnets in VPC $VPC_ID"
    exit 1
fi

# Convert space-separated to comma-separated for AWS CLI
SUBNET_LIST=$(echo $SUBNET_IDS | tr ' ' ',')
print_success "Found subnets: $SUBNET_LIST"

# Step 4: Create or find security group
print_status "Setting up security group..."

SG_NAME="lambda-webapp-sg"
SECURITY_GROUP_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --query "SecurityGroups[0].GroupId" \
    --output text 2>/dev/null || echo "None")

if [ "$SECURITY_GROUP_ID" = "None" ] || [ -z "$SECURITY_GROUP_ID" ]; then
    print_status "Creating security group..."
    SECURITY_GROUP_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "Security group for webapp Lambda function" \
        --vpc-id "$VPC_ID" \
        --query "GroupId" \
        --output text)
    
    # Add outbound rule for all traffic (Lambda needs internet access)
    aws ec2 authorize-security-group-egress \
        --group-id "$SECURITY_GROUP_ID" \
        --protocol -1 \
        --cidr 0.0.0.0/0 >/dev/null || true
    
    print_success "Created security group: $SECURITY_GROUP_ID"
else
    print_success "Found existing security group: $SECURITY_GROUP_ID"
fi

# Step 5: Update Lambda function configuration
print_status "Updating Lambda function configuration..."

# Update environment variables
print_status "Setting environment variables..."
aws lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION" \
    --environment Variables="{
        DB_SECRET_ARN=$SECRET_ARN,
        WEBAPP_AWS_REGION=$AWS_REGION,
        NODE_ENV=production,
        AWS_DEFAULT_REGION=$AWS_REGION
    }" >/dev/null

print_success "Environment variables updated"

# Update VPC configuration
print_status "Updating VPC configuration..."
aws lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION" \
    --vpc-config SubnetIds="$SUBNET_LIST",SecurityGroupIds="$SECURITY_GROUP_ID" >/dev/null

print_success "VPC configuration updated"

# Step 6: Ensure Lambda has proper IAM permissions
print_status "Checking IAM permissions..."

# Get the Lambda's execution role
EXECUTION_ROLE=$(aws lambda get-function \
    --function-name "$LAMBDA_FUNCTION" \
    --query "Configuration.Role" \
    --output text)

print_status "Lambda execution role: $EXECUTION_ROLE"

# Extract role name from ARN
ROLE_NAME=$(echo "$EXECUTION_ROLE" | cut -d'/' -f2)

# Check if the role has Secrets Manager permissions
HAS_SECRETS_PERMISSION=$(aws iam list-attached-role-policies \
    --role-name "$ROLE_NAME" \
    --query "AttachedPolicies[?contains(PolicyName, 'Secrets')]" \
    --output text 2>/dev/null || echo "")

if [ -z "$HAS_SECRETS_PERMISSION" ]; then
    print_status "Adding Secrets Manager permissions..."
    
    # Create and attach a policy for Secrets Manager access
    POLICY_DOC=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": "$SECRET_ARN"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ec2:CreateNetworkInterface",
                "ec2:DescribeNetworkInterfaces",
                "ec2:DeleteNetworkInterface",
                "ec2:AttachNetworkInterface",
                "ec2:DetachNetworkInterface"
            ],
            "Resource": "*"
        }
    ]
}
EOF
)

    # Create inline policy
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "SecretsManagerAndVPCAccess" \
        --policy-document "$POLICY_DOC" >/dev/null
    
    print_success "Added Secrets Manager and VPC permissions"
else
    print_success "Role already has Secrets Manager permissions"
fi

# Step 7: Wait for configuration to propagate and test
print_status "Waiting for configuration to propagate (30 seconds)..."
sleep 30

# Step 8: Test the Lambda function
print_status "Testing Lambda function..."

# Get the API Gateway URL
API_URL="https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev"

print_status "Testing API endpoints..."

# Test root endpoint
if curl -s -f "$API_URL" >/dev/null; then
    print_success "✅ Root endpoint is responding"
else
    print_warning "⚠️ Root endpoint test failed"
fi

# Test health endpoint
if curl -s -f "$API_URL/health?quick=true" >/dev/null; then
    print_success "✅ Health endpoint is responding"
else
    print_warning "⚠️ Health endpoint test failed"
fi

# Test stocks endpoint
STOCKS_RESPONSE=$(curl -s "$API_URL/api/stocks?limit=1" 2>/dev/null || echo "")
if echo "$STOCKS_RESPONSE" | grep -q "success\|data"; then
    print_success "✅ Stocks endpoint is working with database"
else
    print_warning "⚠️ Stocks endpoint may have database issues"
    echo "Response preview: $(echo "$STOCKS_RESPONSE" | head -c 200)..."
fi

print_success "🎉 Lambda function configuration updated!"
echo ""
print_success "Configuration Summary:"
print_success "- Lambda Function: $LAMBDA_FUNCTION"
print_success "- Database Secret: $SECRET_ARN"
print_success "- VPC: $VPC_ID"
print_success "- Security Group: $SECURITY_GROUP_ID"
print_success "- Subnets: $SUBNET_LIST"
echo ""
print_status "Test your endpoints:"
print_status "- API Health: $API_URL/health"
print_status "- Stocks API: $API_URL/api/stocks"
print_status "- Stock Screen: $API_URL/api/stocks/screen"