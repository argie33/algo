#!/bin/bash

# HFT System AWS Deployment Script
# This script deploys the HFT system to AWS ECS with all required infrastructure

set -e

# Configuration
CLUSTER_NAME="hft-cluster"
SERVICE_NAME="hft-system"
TASK_DEFINITION="hft-task"
REGION="us-east-1"
ECR_REPOSITORY="hft-system"
VPC_STACK_NAME="hft-vpc-stack"
ECS_STACK_NAME="hft-ecs-stack"
RDS_STACK_NAME="hft-rds-stack"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required tools
check_requirements() {
    echo "Checking requirements..."
    
    if ! command -v aws &> /dev/null; then
        echo_error "AWS CLI is required but not installed."
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo_error "Docker is required but not installed."
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        echo_error "jq is required but not installed."
        exit 1
    fi
    
    echo_success "All requirements met"
}

# Build and push Docker image
build_and_push_image() {
    echo "Building and pushing Docker image..."
    
    # Get AWS account ID
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    
    # ECR login
    aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
    
    # Create ECR repository if it doesn't exist
    aws ecr describe-repositories --repository-names $ECR_REPOSITORY --region $REGION || \
    aws ecr create-repository --repository-name $ECR_REPOSITORY --region $REGION
    
    # Build image
    docker build -t $ECR_REPOSITORY .
    
    # Tag image
    docker tag $ECR_REPOSITORY:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:latest
    
    # Push image
    docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:latest
    
    echo_success "Docker image built and pushed"
}

# Deploy VPC infrastructure
deploy_vpc() {
    echo "Deploying VPC infrastructure..."
    
    aws cloudformation deploy \
        --template-file infrastructure/vpc.yml \
        --stack-name $VPC_STACK_NAME \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=production \
            ProjectName=hft-system
    
    echo_success "VPC infrastructure deployed"
}

# Deploy RDS infrastructure
deploy_rds() {
    echo "Deploying RDS infrastructure..."
    
    # Get VPC outputs
    VPC_ID=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='VPCId'].OutputValue" --output text)
    PRIVATE_SUBNET_1=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet1'].OutputValue" --output text)
    PRIVATE_SUBNET_2=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet2'].OutputValue" --output text)
    
    aws cloudformation deploy \
        --template-file infrastructure/rds.yml \
        --stack-name $RDS_STACK_NAME \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=production \
            VPCId=$VPC_ID \
            PrivateSubnet1=$PRIVATE_SUBNET_1 \
            PrivateSubnet2=$PRIVATE_SUBNET_2 \
            DBPassword=$(aws secretsmanager get-random-password --password-length 32 --exclude-characters '"@/\' --query RandomPassword --output text)
    
    echo_success "RDS infrastructure deployed"
}

# Deploy ECS infrastructure
deploy_ecs() {
    echo "Deploying ECS infrastructure..."
    
    # Get required parameters
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    VPC_ID=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='VPCId'].OutputValue" --output text)
    PUBLIC_SUBNET_1=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PublicSubnet1'].OutputValue" --output text)
    PUBLIC_SUBNET_2=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PublicSubnet2'].OutputValue" --output text)
    PRIVATE_SUBNET_1=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet1'].OutputValue" --output text)
    PRIVATE_SUBNET_2=$(aws cloudformation describe-stacks --stack-name $VPC_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='PrivateSubnet2'].OutputValue" --output text)
    
    aws cloudformation deploy \
        --template-file infrastructure/ecs.yml \
        --stack-name $ECS_STACK_NAME \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=production \
            ServiceName=$SERVICE_NAME \
            ClusterName=$CLUSTER_NAME \
            VPCId=$VPC_ID \
            PublicSubnet1=$PUBLIC_SUBNET_1 \
            PublicSubnet2=$PUBLIC_SUBNET_2 \
            PrivateSubnet1=$PRIVATE_SUBNET_1 \
            PrivateSubnet2=$PRIVATE_SUBNET_2 \
            ContainerImage=$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:latest
    
    echo_success "ECS infrastructure deployed"
}

# Update ECS service
update_service() {
    echo "Updating ECS service..."
    
    # Force new deployment
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $SERVICE_NAME \
        --force-new-deployment \
        --region $REGION
    
    # Wait for deployment to complete
    aws ecs wait services-stable \
        --cluster $CLUSTER_NAME \
        --services $SERVICE_NAME \
        --region $REGION
    
    echo_success "ECS service updated"
}

# Setup monitoring
setup_monitoring() {
    echo "Setting up monitoring..."
    
    # Create CloudWatch dashboard
    aws cloudformation deploy \
        --template-file infrastructure/monitoring.yml \
        --stack-name hft-monitoring-stack \
        --region $REGION \
        --capabilities CAPABILITY_IAM \
        --parameter-overrides \
            Environment=production \
            ClusterName=$CLUSTER_NAME \
            ServiceName=$SERVICE_NAME
    
    echo_success "Monitoring setup complete"
}

# Main deployment function
deploy() {
    echo "Starting HFT System deployment to AWS..."
    
    check_requirements
    build_and_push_image
    deploy_vpc
    deploy_rds
    deploy_ecs
    update_service
    setup_monitoring
    
    echo_success "HFT System deployment completed successfully!"
    
    # Get service URL
    ALB_DNS=$(aws cloudformation describe-stacks --stack-name $ECS_STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDNS'].OutputValue" --output text)
    echo "Service available at: http://$ALB_DNS"
}

# Rollback function
rollback() {
    echo "Rolling back HFT System deployment..."
    
    # Delete stacks in reverse order
    aws cloudformation delete-stack --stack-name hft-monitoring-stack --region $REGION || true
    aws cloudformation delete-stack --stack-name $ECS_STACK_NAME --region $REGION || true
    aws cloudformation delete-stack --stack-name $RDS_STACK_NAME --region $REGION || true
    aws cloudformation delete-stack --stack-name $VPC_STACK_NAME --region $REGION || true
    
    echo_success "Rollback completed"
}

# Script usage
usage() {
    echo "Usage: $0 [deploy|update|rollback|status]"
    echo "  deploy   - Full deployment of HFT system"
    echo "  update   - Update existing deployment"
    echo "  rollback - Remove all AWS resources"
    echo "  status   - Check deployment status"
}

# Check deployment status
status() {
    echo "Checking HFT System deployment status..."
    
    # Check stack statuses
    for stack in $VPC_STACK_NAME $RDS_STACK_NAME $ECS_STACK_NAME; do
        STATUS=$(aws cloudformation describe-stacks --stack-name $stack --region $REGION --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "NOT_FOUND")
        echo "Stack $stack: $STATUS"
    done
    
    # Check ECS service status
    SERVICE_STATUS=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].status" --output text 2>/dev/null || echo "NOT_FOUND")
    echo "ECS Service: $SERVICE_STATUS"
    
    # Check running tasks
    RUNNING_TASKS=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $REGION --query "services[0].runningCount" --output text 2>/dev/null || echo "0")
    echo "Running Tasks: $RUNNING_TASKS"
}

# Main script logic
case "${1:-}" in
    deploy)
        deploy
        ;;
    update)
        build_and_push_image
        update_service
        ;;
    rollback)
        rollback
        ;;
    status)
        status
        ;;
    *)
        usage
        exit 1
        ;;
esac
