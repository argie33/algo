#!/bin/bash

# Fix TechnicalsDaily ECS Deployment Issue
# This script builds and pushes the missing Docker image to ECR

set -e

echo "🔧 Fixing TechnicalsDaily ECS Deployment Issue..."

# Configuration
REGION="us-east-1"
ECR_REPOSITORY="stocks-app-registry"
IMAGE_NAME="technicalsdaily"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPOSITORY}"

# Get the current git commit hash for tagging
COMMIT_HASH=$(git rev-parse HEAD)
IMAGE_TAG="${IMAGE_NAME}-${COMMIT_HASH}"

echo "📋 Configuration:"
echo "   ECR Repository: ${ECR_URI}"
echo "   Image Tag: ${IMAGE_TAG}"
echo "   Commit Hash: ${COMMIT_HASH}"

# 1. Ensure ECR repository exists
echo "🔍 Checking ECR repository..."
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${REGION} || {
    echo "📦 Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${REGION}
}

# 2. Get ECR login
echo "🔑 Getting ECR login..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# 3. Build Docker image
echo "🏗️  Building Docker image..."
docker build -f Dockerfile.technicalsdaily -t ${IMAGE_TAG} .

# 4. Tag image for ECR
echo "🏷️  Tagging image for ECR..."
docker tag ${IMAGE_TAG} ${ECR_URI}:${IMAGE_TAG}

# 5. Push to ECR
echo "📤 Pushing image to ECR..."
docker push ${ECR_URI}:${IMAGE_TAG}

# 6. Also push as 'latest' for convenience
echo "📤 Pushing as 'latest'..."
docker tag ${IMAGE_TAG} ${ECR_URI}:${IMAGE_NAME}-latest
docker push ${ECR_URI}:${IMAGE_NAME}-latest

# 7. Update ECS task definition (optional)
echo "🔄 Image pushed successfully!"
echo "   Full image URI: ${ECR_URI}:${IMAGE_TAG}"
echo "   You can now run the ECS task with this image"

# 8. Test the container locally (optional)
echo "🧪 Testing container locally..."
docker run --rm -e DB_SECRET_ARN=test-secret -e AWS_DEFAULT_REGION=${REGION} ${IMAGE_TAG} --help || {
    echo "⚠️  Container test failed, but image was pushed successfully"
}

echo "✅ TechnicalsDaily deployment fix complete!"
echo "   Next steps:"
echo "   1. Update your ECS task definition to use: ${ECR_URI}:${IMAGE_TAG}"
echo "   2. Or re-run your GitHub Actions workflow"