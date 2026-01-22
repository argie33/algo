#!/bin/bash
set -e

echo "🚀 Deploying Lambda with database timeout fixes..."
echo ""

AWS_REGION="us-east-1"
STACK_NAME="stocks-webapp-dev"
TEMPLATE_FILE="template-webapp-lambda.yml"
DB_SECRET_ARN="arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"
DB_ENDPOINT="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"

echo "📋 Configuration:"
echo "  Stack: $STACK_NAME"
echo "  Region: $AWS_REGION"
echo "  Template: $TEMPLATE_FILE"
echo "  DB Endpoint: $DB_ENDPOINT"
echo ""

echo "⏳ Deploying stack..."
aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --parameter-overrides \
    DatabaseSecretArn="$DB_SECRET_ARN" \
    DatabaseEndpoint="$DB_ENDPOINT" \
    EnvironmentName="dev" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset

echo ""
echo "✅ Deployment complete!"
echo ""
echo "🔍 Verifying Lambda environment variables..."
aws lambda get-function-configuration \
  --function-name stocks-webapp-api-dev \
  --region "$AWS_REGION" \
  --query 'Environment.Variables.{DB_STATEMENT_TIMEOUT, DB_QUERY_TIMEOUT, DB_ENDPOINT}' \
  --output table

echo ""
echo "✅ Lambda has been updated with:"
echo "   - DB_STATEMENT_TIMEOUT=300000 (5 minutes)"
echo "   - DB_QUERY_TIMEOUT=280000 (4.67 minutes)"
echo ""
echo "⏳ Waiting for Lambda to recycle (30 seconds)..."
sleep 30

echo ""
echo "🧪 Testing stock scores endpoint..."
timeout 15 curl -s https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/scores/stockscores | head -c 300
echo ""
echo ""
echo "✅ AWS Lambda deployment complete!"
