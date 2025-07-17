#!/bin/bash

# Simple Data Loading Trigger Script
# This script provides a straightforward way to trigger data loading tasks
# that bypasses the complex orchestration system

set -e

# Configuration
AWS_REGION="us-east-1"
CLUSTER_STACK="stocks-app-stack"
TASKS_STACK="stocks-ecs-tasks-stack"

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

# Function to get CloudFormation output
get_cf_output() {
    local stack_name=$1
    local output_key=$2
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --region "$AWS_REGION"
}

# Function to run a single ECS task
run_ecs_task() {
    local task_name=$1
    local task_def_output_key=$2
    
    print_status "Running $task_name data loading task..."
    
    # Get infrastructure details
    print_status "Fetching infrastructure configuration..."
    local cluster_arn=$(get_cf_output "$CLUSTER_STACK" "EcsClusterArn")
    local subnets=$(get_cf_output "$CLUSTER_STACK" "DataSubnetIds")
    local security_group=$(get_cf_output "$CLUSTER_STACK" "DataSecurityGroupId")
    local task_def_arn=$(get_cf_output "$TASKS_STACK" "$task_def_output_key")
    
    if [ -z "$cluster_arn" ] || [ -z "$subnets" ] || [ -z "$security_group" ] || [ -z "$task_def_arn" ]; then
        print_error "Failed to fetch required infrastructure details"
        print_error "  Cluster: $cluster_arn"
        print_error "  Subnets: $subnets"
        print_error "  Security Group: $security_group"
        print_error "  Task Definition: $task_def_arn"
        return 1
    fi
    
    print_status "Infrastructure details:"
    print_status "  Cluster: $cluster_arn"
    print_status "  Task Definition: $task_def_arn"
    
    # Run the ECS task
    print_status "Starting ECS task..."
    local task_arn=$(aws ecs run-task \
        --cluster "$cluster_arn" \
        --task-definition "$task_def_arn" \
        --launch-type FARGATE \
        --network-configuration "awsvpcConfiguration={subnets=[$subnets],securityGroups=[$security_group],assignPublicIp=DISABLED}" \
        --count 1 \
        --query 'tasks[0].taskArn' \
        --output text \
        --region "$AWS_REGION")
    
    if [ "$task_arn" = "None" ] || [ -z "$task_arn" ]; then
        print_error "Failed to start ECS task"
        return 1
    fi
    
    print_success "ECS task started successfully"
    print_status "Task ARN: $task_arn"
    
    # Wait for task to complete
    print_status "Waiting for task to complete..."
    aws ecs wait tasks-stopped \
        --cluster "$cluster_arn" \
        --tasks "$task_arn" \
        --region "$AWS_REGION"
    
    # Check task exit code
    local exit_code=$(aws ecs describe-tasks \
        --cluster "$cluster_arn" \
        --tasks "$task_arn" \
        --query 'tasks[0].containers[0].exitCode' \
        --output text \
        --region "$AWS_REGION")
    
    if [ "$exit_code" = "0" ]; then
        print_success "$task_name data loading completed successfully"
        return 0
    else
        print_error "$task_name data loading failed with exit code: $exit_code"
        return 1
    fi
}

# Main function
main() {
    local task_name=${1:-"symbols"}
    
    print_status "Simple Data Loading Trigger"
    print_status "=========================="
    print_status "Task: $task_name"
    print_status "Region: $AWS_REGION"
    print_status ""
    
    # Map task names to CloudFormation output keys
    case "$task_name" in
        "symbols")
            run_ecs_task "Stock Symbols" "SymbolsTaskDefArn"
            ;;
        "info")
            run_ecs_task "Stock Info" "LoadInfoTaskDefArn"
            ;;
        "prices")
            run_ecs_task "Price Data" "PriceDailyTaskDefArn"
            ;;
        "technicals")
            run_ecs_task "Technical Data" "TechnicalsDailyTaskDefArn"
            ;;
        "earnings")
            run_ecs_task "Earnings Data" "EarningsEstimateTaskDefArn"
            ;;
        "news")
            run_ecs_task "News Data" "LoadNewsTaskDefArn"
            ;;
        "sentiment")
            run_ecs_task "Sentiment Data" "SentimentTaskDefArn"
            ;;
        *)
            print_error "Unknown task: $task_name"
            print_status "Available tasks: symbols, info, prices, technicals, earnings, news, sentiment"
            exit 1
            ;;
    esac
}

# Help function
show_help() {
    echo "Simple Data Loading Trigger Script"
    echo ""
    echo "Usage: $0 [task_name]"
    echo ""
    echo "Available tasks:"
    echo "  symbols     - Load stock symbols (default)"
    echo "  info        - Load stock info"
    echo "  prices      - Load price data"
    echo "  technicals  - Load technical data"
    echo "  earnings    - Load earnings data"
    echo "  news        - Load news data"
    echo "  sentiment   - Load sentiment data"
    echo ""
    echo "Examples:"
    echo "  $0 symbols"
    echo "  $0 info"
    echo "  $0 prices"
    echo ""
}

# Check for help flag
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
    exit 0
fi

# Run main function
main "$@"