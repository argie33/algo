#!/bin/bash
# Admin-only script to get the Lambda API endpoint
# This requires AWS permissions for Terraform state access and API Gateway

set -e

echo "=================================="
echo "Getting Lambda API Endpoint"
echo "=================================="
echo ""

# Try Terraform output first
if command -v terraform &> /dev/null; then
    echo "[1] Trying Terraform output..."
    cd terraform || { echo "ERROR: terraform/ directory not found"; exit 1; }

    API_ENDPOINT=$(terraform output api_url -raw 2>/dev/null || echo "")

    if [ ! -z "$API_ENDPOINT" ]; then
        echo "    SUCCESS: Got endpoint from Terraform"
        echo ""
        echo "API ENDPOINT:"
        echo "============="
        echo "$API_ENDPOINT"
        echo ""
        echo "To use in dashboard:"
        echo "  export DASHBOARD_API_URL='$API_ENDPOINT'"
        echo "  python tools/dashboard/dashboard.py"
        echo ""
        exit 0
    fi

    cd ..
fi

# Try AWS API Gateway
echo "[2] Trying AWS API Gateway..."
API_ENDPOINT=$(aws apigatewayv2 get-apis \
    --region us-east-1 \
    --query "Items[?contains(Name, 'algo-api')].ApiEndpoint" \
    --output text 2>/dev/null || echo "")

if [ ! -z "$API_ENDPOINT" ] && [ "$API_ENDPOINT" != "None" ]; then
    echo "    SUCCESS: Got endpoint from AWS API Gateway"
    echo ""
    echo "API ENDPOINT:"
    echo "============="
    echo "$API_ENDPOINT"
    echo ""
    echo "To use in dashboard:"
    echo "  export DASHBOARD_API_URL='$API_ENDPOINT'"
    echo "  python tools/dashboard/dashboard.py"
    echo ""
    exit 0
fi

# Try Lambda function URL
echo "[3] Trying Lambda function URL..."
FUNC_URL=$(aws lambda get-function-url-config \
    --function-name algo-api-dev \
    --region us-east-1 \
    --query "FunctionUrl" \
    --output text 2>/dev/null || echo "")

if [ ! -z "$FUNC_URL" ] && [ "$FUNC_URL" != "None" ]; then
    echo "    SUCCESS: Got endpoint from Lambda function URL"
    echo ""
    echo "API ENDPOINT:"
    echo "============="
    echo "$FUNC_URL"
    echo ""
    echo "To use in dashboard:"
    echo "  export DASHBOARD_API_URL='$FUNC_URL'"
    echo "  python tools/dashboard/dashboard.py"
    echo ""
    exit 0
fi

echo "ERROR: Could not get API endpoint from any source"
echo ""
echo "This script requires AWS permissions for:"
echo "  - terraform output access (S3 backend)"
echo "  - apigateway:GetApis"
echo "  - lambda:GetFunctionUrlConfig"
echo ""
echo "Ask your AWS admin to run this script."
exit 1
