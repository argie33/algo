#!/bin/bash

# AI Agent Infrastructure Deployment Script
# Deploys AI infrastructure integrated with existing Financial Dashboard

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
INFRASTRUCTURE_DIR="$PROJECT_ROOT/infrastructure"

# Default values
ENVIRONMENT="${ENVIRONMENT:-dev}"
PROJECT_NAME="${PROJECT_NAME:-stocks-webapp}"
DEPLOYMENT_TYPE="${DEPLOYMENT_TYPE:-terraform}"  # terraform or cloudformation
AWS_REGION="${AWS_REGION:-us-east-1}"
SKIP_DATABASE_SETUP="${SKIP_DATABASE_SETUP:-false}"
VALIDATE_ONLY="${VALIDATE_ONLY:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
AI Agent Infrastructure Deployment Script

Usage: $0 [OPTIONS]

OPTIONS:
    -e, --environment ENV       Deployment environment (dev, staging, prod) [default: dev]
    -p, --project-name NAME     Project name [default: stocks-webapp]
    -r, --region REGION         AWS region [default: us-east-1]
    -t, --type TYPE             Deployment type (terraform, cloudformation) [default: terraform]
    -s, --skip-db-setup         Skip database setup [default: false]
    -v, --validate-only         Only validate configuration [default: false]
    -h, --help                  Show this help message

EXAMPLES:
    # Deploy to dev environment using Terraform
    $0 --environment dev --type terraform

    # Deploy to production using CloudFormation
    $0 --environment prod --type cloudformation

    # Validate configuration only
    $0 --validate-only

ENVIRONMENT VARIABLES:
    AWS_PROFILE                 AWS profile to use
    DATABASE_ENDPOINT           Existing database endpoint
    VPC_ID                      Existing VPC ID
    PRIVATE_SUBNET_IDS          Comma-separated private subnet IDs
    PUBLIC_SUBNET_IDS           Comma-separated public subnet IDs
    LAMBDA_SECURITY_GROUP_ID    Existing Lambda security group ID (optional)

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -p|--project-name)
            PROJECT_NAME="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -t|--type)
            DEPLOYMENT_TYPE="$2"
            shift 2
            ;;
        -s|--skip-db-setup)
            SKIP_DATABASE_SETUP="true"
            shift
            ;;
        -v|--validate-only)
            VALIDATE_ONLY="true"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    log_error "Environment must be one of: dev, staging, prod"
    exit 1
fi

# Validate deployment type
if [[ ! "$DEPLOYMENT_TYPE" =~ ^(terraform|cloudformation)$ ]]; then
    log_error "Deployment type must be one of: terraform, cloudformation"
    exit 1
fi

log_info "AI Agent Infrastructure Deployment"
log_info "=================================="
log_info "Environment: $ENVIRONMENT"
log_info "Project: $PROJECT_NAME"
log_info "Region: $AWS_REGION"
log_info "Deployment Type: $DEPLOYMENT_TYPE"
log_info "Validate Only: $VALIDATE_ONLY"

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is required but not installed"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or invalid"
        exit 1
    fi
    
    # Check deployment tool
    if [[ "$DEPLOYMENT_TYPE" == "terraform" ]]; then
        if ! command -v terraform &> /dev/null; then
            log_error "Terraform is required but not installed"
            exit 1
        fi
    elif [[ "$DEPLOYMENT_TYPE" == "cloudformation" ]]; then
        # AWS CLI is sufficient for CloudFormation
        :
    fi
    
    # Check Node.js for Lambda packaging
    if ! command -v node &> /dev/null; then
        log_error "Node.js is required for Lambda function packaging"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Get existing infrastructure information
get_existing_infrastructure() {
    log_info "Gathering existing infrastructure information..."
    
    # Try to get database endpoint from CloudFormation stack
    if [[ -z "$DATABASE_ENDPOINT" ]]; then
        DATABASE_ENDPOINT=$(aws cloudformation describe-stacks \
            --stack-name "${PROJECT_NAME}-${ENVIRONMENT}-database" \
            --query 'Stacks[0].Outputs[?OutputKey==`DatabaseEndpoint`].OutputValue' \
            --output text 2>/dev/null || echo "")
    fi
    
    # Try to get VPC information
    if [[ -z "$VPC_ID" ]]; then
        VPC_ID=$(aws cloudformation describe-stacks \
            --stack-name "${PROJECT_NAME}-${ENVIRONMENT}-network" \
            --query 'Stacks[0].Outputs[?OutputKey==`VpcId`].OutputValue' \
            --output text 2>/dev/null || echo "")
    fi
    
    # Try to get subnet information
    if [[ -z "$PRIVATE_SUBNET_IDS" ]]; then
        PRIVATE_SUBNET_IDS=$(aws cloudformation describe-stacks \
            --stack-name "${PROJECT_NAME}-${ENVIRONMENT}-network" \
            --query 'Stacks[0].Outputs[?OutputKey==`PrivateSubnetIds`].OutputValue' \
            --output text 2>/dev/null || echo "")
    fi
    
    if [[ -z "$PUBLIC_SUBNET_IDS" ]]; then
        PUBLIC_SUBNET_IDS=$(aws cloudformation describe-stacks \
            --stack-name "${PROJECT_NAME}-${ENVIRONMENT}-network" \
            --query 'Stacks[0].Outputs[?OutputKey==`PublicSubnetIds`].OutputValue' \
            --output text 2>/dev/null || echo "")
    fi
    
    # Validate required variables
    if [[ -z "$DATABASE_ENDPOINT" ]] || [[ -z "$VPC_ID" ]] || [[ -z "$PRIVATE_SUBNET_IDS" ]]; then
        log_error "Missing required infrastructure information:"
        log_error "  DATABASE_ENDPOINT: ${DATABASE_ENDPOINT:-'NOT FOUND'}"
        log_error "  VPC_ID: ${VPC_ID:-'NOT FOUND'}"
        log_error "  PRIVATE_SUBNET_IDS: ${PRIVATE_SUBNET_IDS:-'NOT FOUND'}"
        log_error ""
        log_error "Please set these as environment variables or ensure existing CloudFormation stacks exist"
        exit 1
    fi
    
    log_success "Infrastructure information gathered"
    log_info "  Database: $DATABASE_ENDPOINT"
    log_info "  VPC: $VPC_ID"
    log_info "  Private Subnets: $PRIVATE_SUBNET_IDS"
    log_info "  Public Subnets: ${PUBLIC_SUBNET_IDS:-'Not specified'}"
}

# Validate Bedrock access
validate_bedrock_access() {
    log_info "Validating AWS Bedrock access..."
    
    # Check if Bedrock is available in the region
    if ! aws bedrock list-foundation-models --region "$AWS_REGION" &> /dev/null; then
        log_error "AWS Bedrock is not accessible in region $AWS_REGION"
        log_error "Please ensure:"
        log_error "  1. Bedrock is available in your region"
        log_error "  2. You have the necessary IAM permissions"
        log_error "  3. Claude models are enabled in Bedrock console"
        exit 1
    fi
    
    # Check for Claude 3 Haiku model
    CLAUDE_HAIKU_AVAILABLE=$(aws bedrock list-foundation-models \
        --region "$AWS_REGION" \
        --query 'modelSummaries[?modelId==`anthropic.claude-3-haiku-20240307-v1:0`]' \
        --output json | jq length)
    
    if [[ "$CLAUDE_HAIKU_AVAILABLE" == "0" ]]; then
        log_warning "Claude 3 Haiku model not found in available models"
        log_warning "Please enable Claude 3 models in the AWS Bedrock console"
    else
        log_success "Claude 3 Haiku model is available"
    fi
}

# Deploy using Terraform
deploy_terraform() {
    log_info "Deploying AI infrastructure using Terraform..."
    
    cd "$INFRASTRUCTURE_DIR/terraform"
    
    # Initialize Terraform
    log_info "Initializing Terraform..."
    terraform init
    
    # Create terraform.tfvars
    cat > terraform.tfvars << EOF
environment = "$ENVIRONMENT"
project_name = "$PROJECT_NAME"
vpc_id = "$VPC_ID"
private_subnet_ids = [$(echo "$PRIVATE_SUBNET_IDS" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')
]
database_endpoint = "$DATABASE_ENDPOINT"
lambda_security_group_id = "${LAMBDA_SECURITY_GROUP_ID:-}"
EOF

    if [[ -n "$PUBLIC_SUBNET_IDS" ]]; then
        echo "public_subnet_ids = [$(echo "$PUBLIC_SUBNET_IDS" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')
]" >> terraform.tfvars
    fi
    
    # Plan
    log_info "Creating Terraform execution plan..."
    terraform plan -var-file=terraform.tfvars -out=tfplan
    
    if [[ "$VALIDATE_ONLY" == "true" ]]; then
        log_success "Terraform validation completed successfully"
        return 0
    fi
    
    # Apply
    log_info "Applying Terraform configuration..."
    terraform apply tfplan
    
    # Output important values
    log_success "Terraform deployment completed"
    log_info "Important outputs:"
    terraform output
}

# Deploy using CloudFormation
deploy_cloudformation() {
    log_info "Deploying AI infrastructure using CloudFormation..."
    
    local stack_name="${PROJECT_NAME}-${ENVIRONMENT}-ai-agent"
    local template_path="$INFRASTRUCTURE_DIR/cloudformation/ai-agent-infrastructure.yml"
    
    # Prepare parameters
    local parameters=""
    parameters+="ParameterKey=Environment,ParameterValue=$ENVIRONMENT "
    parameters+="ParameterKey=ProjectName,ParameterValue=$PROJECT_NAME "
    parameters+="ParameterKey=VpcId,ParameterValue=$VPC_ID "
    parameters+="ParameterKey=PrivateSubnetIds,ParameterValue=\"$PRIVATE_SUBNET_IDS\" "
    parameters+="ParameterKey=DatabaseEndpoint,ParameterValue=$DATABASE_ENDPOINT "
    
    if [[ -n "$PUBLIC_SUBNET_IDS" ]]; then
        parameters+="ParameterKey=PublicSubnetIds,ParameterValue=\"$PUBLIC_SUBNET_IDS\" "
    fi
    
    if [[ -n "$LAMBDA_SECURITY_GROUP_ID" ]]; then
        parameters+="ParameterKey=LambdaSecurityGroupId,ParameterValue=$LAMBDA_SECURITY_GROUP_ID "
    fi
    
    # Validate template
    log_info "Validating CloudFormation template..."
    aws cloudformation validate-template --template-body file://"$template_path"
    
    if [[ "$VALIDATE_ONLY" == "true" ]]; then
        log_success "CloudFormation validation completed successfully"
        return 0
    fi
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$stack_name" &> /dev/null; then
        log_info "Updating existing CloudFormation stack..."
        aws cloudformation update-stack \
            --stack-name "$stack_name" \
            --template-body file://"$template_path" \
            --parameters $parameters \
            --capabilities CAPABILITY_NAMED_IAM
        
        log_info "Waiting for stack update to complete..."
        aws cloudformation wait stack-update-complete --stack-name "$stack_name"
    else
        log_info "Creating new CloudFormation stack..."
        aws cloudformation create-stack \
            --stack-name "$stack_name" \
            --template-body file://"$template_path" \
            --parameters $parameters \
            --capabilities CAPABILITY_NAMED_IAM
        
        log_info "Waiting for stack creation to complete..."
        aws cloudformation wait stack-create-complete --stack-name "$stack_name"
    fi
    
    # Output stack outputs
    log_success "CloudFormation deployment completed"
    log_info "Stack outputs:"
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue,Description]' \
        --output table
}

# Setup AI database tables
setup_ai_database() {
    if [[ "$SKIP_DATABASE_SETUP" == "true" ]]; then
        log_info "Skipping database setup as requested"
        return 0
    fi
    
    log_info "Setting up AI database tables..."
    
    # Get the database setup Lambda function name
    local lambda_name="${PROJECT_NAME}-${ENVIRONMENT}-ai-db-setup"
    
    # Invoke the database setup Lambda
    log_info "Invoking database setup Lambda function..."
    local result=$(aws lambda invoke \
        --function-name "$lambda_name" \
        --payload '{"action": "setup"}' \
        --region "$AWS_REGION" \
        response.json)
    
    if [[ $(echo "$result" | jq -r '.StatusCode') == "200" ]]; then
        local response_payload=$(cat response.json | jq -r '.')
        if [[ $(echo "$response_payload" | jq -r '.success') == "true" ]]; then
            log_success "AI database tables setup completed"
        else
            log_error "Database setup failed: $(echo "$response_payload" | jq -r '.error')"
            exit 1
        fi
    else
        log_error "Failed to invoke database setup Lambda"
        cat response.json
        exit 1
    fi
    
    rm -f response.json
}

# Test AI infrastructure
test_ai_infrastructure() {
    log_info "Testing AI infrastructure..."
    
    # Test WebSocket API
    local websocket_url=""
    if [[ "$DEPLOYMENT_TYPE" == "terraform" ]]; then
        websocket_url=$(cd "$INFRASTRUCTURE_DIR/terraform" && terraform output -raw ai_websocket_api_url 2>/dev/null || echo "")
    elif [[ "$DEPLOYMENT_TYPE" == "cloudformation" ]]; then
        local stack_name="${PROJECT_NAME}-${ENVIRONMENT}-ai-agent"
        websocket_url=$(aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --query 'Stacks[0].Outputs[?OutputKey==`AIWebSocketApiUrl`].OutputValue' \
            --output text 2>/dev/null || echo "")
    fi
    
    if [[ -n "$websocket_url" ]]; then
        log_success "WebSocket API URL: $websocket_url"
    else
        log_warning "Could not retrieve WebSocket API URL"
    fi
    
    # Test AI processing Lambda
    local lambda_name="${PROJECT_NAME}-${ENVIRONMENT}-ai-processing"
    if aws lambda get-function --function-name "$lambda_name" &> /dev/null; then
        log_success "AI Processing Lambda function is accessible"
    else
        log_warning "AI Processing Lambda function not found or not accessible"
    fi
    
    # Test Bedrock access from Lambda
    log_info "Testing Bedrock access from Lambda..."
    local test_result=$(aws lambda invoke \
        --function-name "$lambda_name" \
        --payload '{"type": "regular_chat", "message": "Hello", "userId": "test-user", "conversationId": "test-conversation"}' \
        --region "$AWS_REGION" \
        test_response.json 2>/dev/null || echo "FAILED")
    
    if [[ "$test_result" != "FAILED" ]]; then
        if [[ $(cat test_response.json | jq -r '.statusCode') == "200" ]]; then
            log_success "AI processing test completed successfully"
        else
            log_warning "AI processing test returned non-200 status"
        fi
    else
        log_warning "Could not test AI processing Lambda"
    fi
    
    rm -f test_response.json
}

# Main deployment function
main() {
    log_info "Starting AI Agent infrastructure deployment..."
    
    check_prerequisites
    get_existing_infrastructure
    validate_bedrock_access
    
    if [[ "$DEPLOYMENT_TYPE" == "terraform" ]]; then
        deploy_terraform
    elif [[ "$DEPLOYMENT_TYPE" == "cloudformation" ]]; then
        deploy_cloudformation
    fi
    
    if [[ "$VALIDATE_ONLY" != "true" ]]; then
        setup_ai_database
        test_ai_infrastructure
        
        log_success "AI Agent infrastructure deployment completed successfully!"
        log_info ""
        log_info "Next steps:"
        log_info "1. Update your frontend environment variables with the WebSocket URL"
        log_info "2. Test the AI chat functionality"
        log_info "3. Monitor CloudWatch logs for any issues"
        log_info "4. Set up monitoring and alerting as needed"
    fi
}

# Run main function
main "$@"