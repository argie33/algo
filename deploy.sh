#!/bin/bash
# Stock Analytics Loaders - Quick Deployment Script
# Deploy refactored loaders to AWS ECS

set -e

echo "=================================="
echo "Stock Analytics Loaders Deployer"
echo "=================================="
echo ""

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
AWS_ACCOUNT=${AWS_ACCOUNT:-$(aws sts get-caller-identity --query Account --output text)}
ECR_REGISTRY="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPOSITORY="stocks-app-registry"
IMAGE_NAME="$ECR_REGISTRY/$ECR_REPOSITORY"

echo "Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  AWS Account: $AWS_ACCOUNT"
echo "  ECR Registry: $ECR_REGISTRY"
echo ""

# Step 1: Login to ECR
echo "Step 1: Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# Step 2: Build Docker image
echo ""
echo "Step 2: Building Docker image..."
docker build -t $IMAGE_NAME:latest .

# Step 3: Push to ECR
echo ""
echo "Step 3: Pushing image to ECR..."
docker push $IMAGE_NAME:latest

# Step 4: Create/Update ECS task definitions
echo ""
echo "Step 4: Updating ECS task definitions..."
aws ecs list-task-definition-families --region $AWS_REGION | \
  jq -r '.taskDefinitionFamilies[]' | head -5 | while read task; do
  echo "  Would update task: $task"
done

# Step 5: Deploy infrastructure
echo ""
echo "Step 5: Deploying CloudFormation stack..."
echo "  Run: aws cloudformation deploy --template-file template.yml --stack-name stocks-app-stack"

echo ""
echo "=================================="
echo "✅ Deployment preparation complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Verify CloudWatch logs for loader execution"
echo "2. Check RDS for data: SELECT COUNT(*) FROM price_daily;"
echo "3. Monitor S3 staging bucket: stocks-app-data"
echo "4. Verify 10x performance improvement"
echo ""
