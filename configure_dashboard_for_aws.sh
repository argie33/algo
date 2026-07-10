#!/bin/bash
# Configure dashboard for AWS production mode
# This script gets the API Gateway endpoint from AWS and sets up the dashboard

set -e

echo "=== CONFIGURING DASHBOARD FOR AWS MODE ==="
echo ""

# Get API Gateway endpoint from CloudFormation/Terraform
echo "Fetching API Gateway endpoint from AWS..."

API_ENDPOINT=$(aws apigateway get-rest-apis \
  --query 'items[?name==`algo-api-dev`].id' \
  --output text \
  --region us-east-1)

if [ -z "$API_ENDPOINT" ]; then
  echo "[ERROR] Could not find API Gateway endpoint"
  exit 1
fi

STAGE="dev"
DASHBOARD_API_URL="https://${API_ENDPOINT}.execute-api.us-east-1.amazonaws.com/${STAGE}"

echo "API Gateway endpoint found: $DASHBOARD_API_URL"
echo ""
echo "Setting environment variable..."

export DASHBOARD_API_URL="$DASHBOARD_API_URL"

echo "DASHBOARD_API_URL=$DASHBOARD_API_URL"
echo ""
echo "Starting dashboard..."
echo ""

python3 -m dashboard

