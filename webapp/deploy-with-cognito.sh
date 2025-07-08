#!/bin/bash
# Deploy Lambda with Cognito Authentication

# Configuration
STACK_NAME="financial-dashboard-webapp"
TEMPLATE_FILE="template-webapp-complete.yml"
ENVIRONMENT="prod"
REGION="us-east-1"

# Get your existing parameters
DB_SECRET_ARN=$(aws secretsmanager list-secrets --region $REGION --query "SecretList[?Name=='financial-dashboard-db-credentials'].ARN | [0]" --output text)

# You need to set these with your actual Cognito values
COGNITO_USER_POOL_ID="YOUR_USER_POOL_ID"  # e.g. us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID="YOUR_CLIENT_ID"        # e.g. XXXXXXXXXXXXXXXXXXXXXXXXXX

# Check if Cognito values are set
if [ "$COGNITO_USER_POOL_ID" = "YOUR_USER_POOL_ID" ] || [ "$COGNITO_CLIENT_ID" = "YOUR_CLIENT_ID" ]; then
    echo "ERROR: Please update this script with your actual Cognito User Pool ID and Client ID"
    echo ""
    echo "To find these values:"
    echo "1. Go to AWS Cognito Console: https://console.aws.amazon.com/cognito/home?region=$REGION"
    echo "2. Select your User Pool"
    echo "3. Copy the User Pool ID from the General settings"
    echo "4. Go to App clients and copy the Client ID"
    exit 1
fi

# Build Lambda
echo "Building Lambda function..."
cd lambda
npm install --production
cd ..

# Deploy CloudFormation stack
echo "Deploying CloudFormation stack..."
sam deploy \
    --stack-name $STACK_NAME \
    --template-file $TEMPLATE_FILE \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides \
        EnvironmentName=$ENVIRONMENT \
        DatabaseSecretArn=$DB_SECRET_ARN \
        CognitoUserPoolId=$COGNITO_USER_POOL_ID \
        CognitoClientId=$COGNITO_CLIENT_ID \
    --region $REGION \
    --no-fail-on-empty-changeset

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful!"
    echo ""
    echo "Your Lambda function now has Cognito authentication configured."
    echo "API Keys endpoint should now work properly."
else
    echo "❌ Deployment failed!"
    exit 1
fi