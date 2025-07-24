#!/bin/bash

# Deploy Enhanced Integration Test Infrastructure
# This script deploys real AWS services for integration testing

set -e

# Configuration
STACK_NAME="algo-integration-test-infrastructure"
TEMPLATE_FILE="cloudformation/enhanced-integration-test-infrastructure.yml"
REGION=${AWS_DEFAULT_REGION:-us-east-1}
ENVIRONMENT="integration-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if AWS CLI is configured
check_aws_config() {
    if ! aws sts get-caller-identity &>/dev/null; then
        print_error "AWS CLI is not configured or credentials are invalid"
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local region=$(aws configure get region)
    print_status "Using AWS Account: $account_id in Region: $region"
}

# Function to validate CloudFormation template
validate_template() {
    print_status "Validating CloudFormation template..."
    if aws cloudformation validate-template --template-body file://$TEMPLATE_FILE &>/dev/null; then
        print_status "Template validation successful"
    else
        print_error "Template validation failed"
        exit 1
    fi
}

# Function to check if stack exists
stack_exists() {
    aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION &>/dev/null
}

# Function to deploy stack
deploy_stack() {
    local action=$1
    
    print_status "Starting $action of stack: $STACK_NAME"
    
    local parameters=(
        "ParameterKey=Environment,ParameterValue=$ENVIRONMENT"
        "ParameterKey=TestDataBucket,ParameterValue=algo-integration-test-data"
    )
    
    if [ "$action" == "create" ]; then
        aws cloudformation create-stack \
            --stack-name $STACK_NAME \
            --template-body file://$TEMPLATE_FILE \
            --parameters "${parameters[@]}" \
            --capabilities CAPABILITY_NAMED_IAM \
            --region $REGION \
            --tags Key=Environment,Value=$ENVIRONMENT Key=Purpose,Value=IntegrationTesting
    else
        aws cloudformation update-stack \
            --stack-name $STACK_NAME \
            --template-body file://$TEMPLATE_FILE \
            --parameters "${parameters[@]}" \
            --capabilities CAPABILITY_NAMED_IAM \
            --region $REGION
    fi
}

# Function to wait for stack operation to complete
wait_for_stack() {
    local operation=$1
    print_status "Waiting for stack $operation to complete..."
    
    if [ "$operation" == "create" ]; then
        aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $REGION
    else
        aws cloudformation wait stack-update-complete --stack-name $STACK_NAME --region $REGION
    fi
    
    if [ $? -eq 0 ]; then
        print_status "Stack $operation completed successfully"
    else
        print_error "Stack $operation failed"
        
        # Show stack events for debugging
        print_status "Recent stack events:"
        aws cloudformation describe-stack-events \
            --stack-name $STACK_NAME \
            --region $REGION \
            --max-items 10 \
            --query 'StackEvents[?ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_FAILED`].[LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
            --output table
        
        exit 1
    fi
}

# Function to initialize test data
initialize_test_data() {
    print_status "Initializing test data..."
    
    # Get the Lambda function name from stack outputs
    local function_name=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`TestDataInitializerFunction`].OutputValue' \
        --output text)
    
    if [ -n "$function_name" ]; then
        aws lambda invoke \
            --function-name "$ENVIRONMENT-data-initializer" \
            --region $REGION \
            --payload '{}' \
            /tmp/lambda-response.json
        
        local status_code=$(cat /tmp/lambda-response.json | jq -r '.statusCode // 200')
        if [ "$status_code" == "200" ]; then
            print_status "Test data initialization completed"
        else
            print_warning "Test data initialization may have failed. Check function logs."
        fi
        
        rm -f /tmp/lambda-response.json
    else
        print_warning "Could not find test data initializer function"
    fi
}

# Function to display stack outputs
display_outputs() {
    print_status "Stack outputs:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue,Description]' \
        --output table
}

# Function to create environment configuration file
create_env_config() {
    print_status "Creating environment configuration file..."
    
    local outputs=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs')
    
    cat > integration-test.env <<EOF
# Integration Test Environment Configuration
# Generated by deploy-integration-test-infrastructure.sh

INTEGRATION_TEST_VPC_ID=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestVPCId") | .OutputValue')
INTEGRATION_TEST_DB_ENDPOINT=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestDatabaseEndpoint") | .OutputValue')
INTEGRATION_TEST_DB_SECRET_ARN=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestDatabaseSecretArn") | .OutputValue')
INTEGRATION_TEST_COGNITO_POOL_ID=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestCognitoUserPoolId") | .OutputValue')
INTEGRATION_TEST_COGNITO_CLIENT_ID=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestCognitoClientId") | .OutputValue')
INTEGRATION_TEST_S3_BUCKET=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestS3Bucket") | .OutputValue')
INTEGRATION_TEST_REDIS_ENDPOINT=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestRedisEndpoint") | .OutputValue')
INTEGRATION_TEST_SQS_QUEUE_URL=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestSQSQueueUrl") | .OutputValue')
INTEGRATION_TEST_SNS_TOPIC_ARN=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestSNSTopicArn") | .OutputValue')
INTEGRATION_TEST_LAMBDA_ROLE_ARN=$(echo $outputs | jq -r '.[] | select(.OutputKey=="TestLambdaExecutionRoleArn") | .OutputValue')

# Test Environment Settings
NODE_ENV=integration-test
AWS_REGION=$REGION
ENVIRONMENT=$ENVIRONMENT
EOF
    
    print_status "Environment configuration saved to integration-test.env"
}

# Function to run basic connectivity tests
run_connectivity_tests() {
    print_status "Running basic connectivity tests..."
    
    # Test database connectivity
    local db_endpoint=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`TestDatabaseEndpoint`].OutputValue' \
        --output text)
    
    if [ -n "$db_endpoint" ]; then
        print_status "Testing database connectivity to $db_endpoint..."
        if timeout 10 bash -c "</dev/tcp/$db_endpoint/5432"; then
            print_status "Database connectivity test passed"
        else
            print_warning "Database connectivity test failed"
        fi
    fi
    
    # Test Redis connectivity
    local redis_endpoint=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --region $REGION \
        --query 'Stacks[0].Outputs[?OutputKey==`TestRedisEndpoint`].OutputValue' \
        --output text)
    
    if [ -n "$redis_endpoint" ]; then
        print_status "Testing Redis connectivity to $redis_endpoint..."
        if timeout 10 bash -c "</dev/tcp/$redis_endpoint/6379"; then
            print_status "Redis connectivity test passed"
        else
            print_warning "Redis connectivity test failed"
        fi
    fi
}

# Function to cleanup on error
cleanup_on_error() {
    print_error "Deployment failed. Cleaning up resources..."
    
    if stack_exists; then
        print_status "Deleting failed stack..."
        aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
        aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION
        print_status "Stack cleanup completed"
    fi
}

# Main execution
main() {
    print_status "Starting integration test infrastructure deployment"
    
    # Trap errors for cleanup
    trap cleanup_on_error ERR
    
    # Pre-deployment checks
    check_aws_config
    validate_template
    
    # Deploy stack
    if stack_exists; then
        print_status "Stack exists. Updating..."
        deploy_stack "update"
        wait_for_stack "update"
    else
        print_status "Stack does not exist. Creating..."
        deploy_stack "create"
        wait_for_stack "create"
    fi
    
    # Post-deployment setup
    initialize_test_data
    create_env_config
    display_outputs
    run_connectivity_tests
    
    print_status "Integration test infrastructure deployment completed successfully!"
    print_status "Environment configuration available in: integration-test.env"
    print_status "Load it with: source integration-test.env"
}

# Script options
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "delete")
        print_status "Deleting integration test infrastructure..."
        if stack_exists; then
            aws cloudformation delete-stack --stack-name $STACK_NAME --region $REGION
            aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME --region $REGION
            print_status "Stack deleted successfully"
            rm -f integration-test.env
        else
            print_warning "Stack does not exist"
        fi
        ;;
    "status")
        if stack_exists; then
            aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION
        else
            print_warning "Stack does not exist"
        fi
        ;;
    "outputs")
        if stack_exists; then
            display_outputs
        else
            print_warning "Stack does not exist"
        fi
        ;;
    *)
        echo "Usage: $0 [deploy|delete|status|outputs]"
        echo "  deploy  - Deploy or update the integration test infrastructure (default)"
        echo "  delete  - Delete the integration test infrastructure"
        echo "  status  - Show current stack status"
        echo "  outputs - Display stack outputs"
        exit 1
        ;;
esac