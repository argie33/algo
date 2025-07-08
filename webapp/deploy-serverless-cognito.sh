#!/bin/bash
# Deploy serverless webapp with Cognito authentication via Secrets Manager

set -e

# Configuration
STACK_NAME="${STACK_NAME:-stocks-serverless-webapp}"
TEMPLATE_FILE="template-webapp-serverless.yml"
REGION="${AWS_REGION:-us-east-1}"
CODE_BUCKET=$(aws cloudformation describe-stacks --stack-name stocks-infra-stack --region $REGION --query "Stacks[0].Outputs[?OutputKey=='CodeBucketName'].OutputValue" --output text)

echo "🚀 Starting serverless webapp deployment with Cognito..."
echo "Stack: $STACK_NAME"
echo "Region: $REGION"
echo "Code Bucket: $CODE_BUCKET"

# Step 1: Build and package Lambda
echo "📦 Building Lambda function..."
cd lambda
npm install --production
zip -r ../api.zip . -x "*.git*" -x "node_modules/aws-sdk/*" -x "tests/*"
cd ..

# Step 2: Upload Lambda code to S3
echo "☁️ Uploading Lambda code to S3..."
aws s3 cp api.zip s3://$CODE_BUCKET/api.zip

# Step 3: Build frontend
echo "🔨 Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Step 4: Deploy CloudFormation stack
echo "🔄 Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file $TEMPLATE_FILE \
    --stack-name $STACK_NAME \
    --parameter-overrides \
        LambdaCodeKey=api.zip \
    --capabilities CAPABILITY_IAM \
    --region $REGION \
    --no-fail-on-empty-changeset

# Step 5: Get outputs
echo "📋 Getting stack outputs..."
FRONTEND_BUCKET=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='FrontendBucket'].OutputValue" --output text 2>/dev/null || echo "")
CLOUDFRONT_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='SPAUrl'].OutputValue" --output text)
API_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" --output text)
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)
CLIENT_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" --output text)
COGNITO_DOMAIN=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='UserPoolDomain'].OutputValue" --output text)
COGNITO_SECRET_ARN=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION --query "Stacks[0].Outputs[?OutputKey=='CognitoConfigSecretArn'].OutputValue" --output text)

# Step 6: Create frontend config
echo "⚙️ Creating frontend runtime configuration..."
cat > frontend/dist/config.js << EOF
window.__CONFIG__ = {
  API_URL: "${API_URL}",
  COGNITO_USER_POOL_ID: "${USER_POOL_ID}",
  COGNITO_CLIENT_ID: "${CLIENT_ID}",
  COGNITO_DOMAIN: "${COGNITO_DOMAIN}",
  AWS_REGION: "${REGION}"
};
EOF

# Step 7: Upload frontend to S3
if [ -z "$FRONTEND_BUCKET" ]; then
    FRONTEND_BUCKET=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'stocks') && contains(Name, 'site-code')].Name" --output text | head -n1)
fi

echo "📤 Uploading frontend to S3 bucket: $FRONTEND_BUCKET"
aws s3 sync frontend/dist/ s3://$FRONTEND_BUCKET/ --delete

# Step 8: Invalidate CloudFront cache
echo "🔄 Invalidating CloudFront cache..."
DISTRIBUTION_ID=$(aws cloudfront list-distributions --query "DistributionList.Items[?Origins.Items[?contains(DomainName, '${FRONTEND_BUCKET}')]].Id" --output text | head -n1)
if [ ! -z "$DISTRIBUTION_ID" ]; then
    aws cloudfront create-invalidation --distribution-id $DISTRIBUTION_ID --paths "/*"
fi

# Clean up
rm -f api.zip

echo "✅ Deployment complete!"
echo ""
echo "🌐 Frontend URL: https://${CLOUDFRONT_URL}"
echo "🔌 API URL: ${API_URL}"
echo "🔐 Cognito User Pool ID: ${USER_POOL_ID}"
echo "🔑 Cognito Client ID: ${CLIENT_ID}"
echo "🌍 Cognito Domain: https://${COGNITO_DOMAIN}"
echo "🔒 Cognito Secret ARN: ${COGNITO_SECRET_ARN}"
echo ""
echo "📝 Note: The Lambda function will automatically load Cognito config from Secrets Manager"
echo "   No manual configuration needed - authentication is fully automated!"