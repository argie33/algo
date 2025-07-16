#!/bin/bash

set -e

echo "🔧 Updating core infrastructure with Lambda security group and site bucket"

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

STACK_NAME="stocks-core-infrastructure"

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name $STACK_NAME >/dev/null 2>&1; then
    print_error "Core infrastructure stack '$STACK_NAME' not found. Please deploy it first."
    exit 1
fi

print_status "Updating core infrastructure stack with Lambda security group and site bucket..."

# Update the stack
aws cloudformation update-stack \
    --stack-name $STACK_NAME \
    --template-body file://template-core.yml \
    --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
    --parameters \
        ParameterKey=VpcCidr,UsePreviousValue=true \
        ParameterKey=PublicSubnetCidr1,UsePreviousValue=true \
        ParameterKey=PublicSubnetCidr2,UsePreviousValue=true \
        ParameterKey=PrivateSubnetCidr1,UsePreviousValue=true \
        ParameterKey=PrivateSubnetCidr2,UsePreviousValue=true \
        ParameterKey=DBStackName,UsePreviousValue=true \
        ParameterKey=DBSecretName,UsePreviousValue=true \
        ParameterKey=BastionInstanceType,UsePreviousValue=true \
        ParameterKey=BastionAmiId,UsePreviousValue=true

print_status "Waiting for stack update to complete..."

# Wait for stack operation to complete
aws cloudformation wait stack-update-complete --stack-name $STACK_NAME

# Check if update was successful
if [ $? -eq 0 ]; then
    print_success "Core infrastructure update completed successfully!"
    
    # Show new outputs
    print_status "Updated stack outputs:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query "Stacks[0].Outputs[?OutputKey=='LambdaSecurityGroupId' || OutputKey=='SiteCodeBucketName'].[OutputKey,OutputValue]" \
        --output table
        
else
    print_error "Stack update failed!"
    
    # Get stack events for debugging
    print_status "Recent stack events:"
    aws cloudformation describe-stack-events \
        --stack-name $STACK_NAME \
        --query "StackEvents[?ResourceStatus=='UPDATE_FAILED'].[LogicalResourceId,ResourceStatus,ResourceStatusReason]" \
        --output table
    exit 1
fi

print_success "Core infrastructure update completed!"