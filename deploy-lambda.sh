#!/bin/bash
set -e

# AWS Configuration
AWS_REGION="us-east-1"
STACK_NAME="stocks-webapp-lambda-api"
TEMPLATE_FILE="template-webapp-lambda.yml"
DB_SECRET_ARN="arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ"
DB_ENDPOINT="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"

echo "📦 Deploying Lambda Stack..."
echo "  Stack Name: $STACK_NAME"
echo "  Region: $AWS_REGION"
echo "  DB Endpoint: $DB_ENDPOINT"
echo "  DB Secret: ${DB_SECRET_ARN:0:80}..."
echo ""

aws cloudformation deploy \
  --template-file "$TEMPLATE_FILE" \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --parameter-overrides \
    DatabaseSecretArn="$DB_SECRET_ARN" \
    DatabaseEndpoint="$DB_ENDPOINT" \
    EnvironmentName="dev" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  2>&1 | tail -50

echo ""
echo "✅ Lambda deployment initiated!"
