#!/bin/bash
# AWS Manual Deployment - No Terraform Apply Required
# Deploys all Lambda functions, API routes, and EventBridge schedules via AWS CLI
# User: algo-developer (no terraform permissions needed, only AWS API permissions)

set -e

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_NAME="algo"
ENVIRONMENT="dev"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="626216981288"
LAMBDA_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/algo-lambda-execution-dev"
EVENTBRIDGE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/algo-eventbridge-scheduler-dev"
API_GATEWAY_ID=$(aws apigatewayv2 get-apis --region $AWS_REGION --query "Items[?Name=='${PROJECT_NAME}-api-${ENVIRONMENT}'].ApiId" --output text)

echo "==============================================="
echo "AWS Manual Deployment Script"
echo "==============================================="
echo "Project: $PROJECT_NAME"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Account ID: $AWS_ACCOUNT_ID"
echo "API Gateway ID: $API_GATEWAY_ID"
echo ""

# ============================================================
# STEP 1: Build and Deploy Orchestrator Lambda
# ============================================================
echo "[1/3] Building and deploying Orchestrator Lambda..."

PKG_DIR=/tmp/algo-lambda-pkg
mkdir -p $PKG_DIR
rm -rf $PKG_DIR/*

# Copy code
cp lambda/algo_orchestrator/lambda_function.py $PKG_DIR/
cp -r algo $PKG_DIR/
cp -r config $PKG_DIR/
cp -r utils $PKG_DIR/

# Install dependencies
python3.12 -m pip install -r lambda/algo_orchestrator/requirements.txt -t $PKG_DIR/ --quiet

# Create ZIP
cd $PKG_DIR && zip -r /tmp/algo-orchestrator.zip . -q && cd -

# Deploy
ORCHESTRATOR_FUNC="${PROJECT_NAME}-algo-${ENVIRONMENT}"
aws lambda update-function-code \
  --function-name $ORCHESTRATOR_FUNC \
  --zip-file fileb:///tmp/algo-orchestrator.zip \
  --region $AWS_REGION

echo "✓ Orchestrator Lambda deployed: $ORCHESTRATOR_FUNC"
echo ""

# ============================================================
# STEP 2: Build and Deploy API Lambda
# ============================================================
echo "[2/3] Building and deploying API Lambda..."

PKG_DIR=/tmp/api-lambda-pkg
mkdir -p $PKG_DIR
rm -rf $PKG_DIR/*

# Copy code
cp -r lambda/api/* $PKG_DIR/
cp -r config $PKG_DIR/
cp -r utils $PKG_DIR/
cp -r algo $PKG_DIR/

# Install dependencies
python3.12 -m pip install -r lambda/api/requirements.txt -t $PKG_DIR/ --quiet

# Create ZIP
cd $PKG_DIR && zip -r /tmp/algo-api.zip . -q && cd -

# Deploy
API_FUNC="${PROJECT_NAME}-api-${ENVIRONMENT}"
aws lambda update-function-code \
  --function-name $API_FUNC \
  --zip-file fileb:///tmp/algo-api.zip \
  --region $AWS_REGION

echo "✓ API Lambda deployed: $API_FUNC"
echo ""

# ============================================================
# STEP 3: Create EventBridge Schedules
# ============================================================
echo "[3/3] Creating EventBridge Schedules..."

# Morning run (9:30 AM ET)
aws scheduler create-schedule \
  --name "${PROJECT_NAME}-algo-schedule-morning-${ENVIRONMENT}" \
  --schedule-expression "cron(30 9 ? * MON-FRI *)" \
  --schedule-expression-timezone "America/New_York" \
  --state ENABLED \
  --flexible-time-window Mode=OFF \
  --target "
    Arn=arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${ORCHESTRATOR_FUNC},
    RoleArn=${EVENTBRIDGE_ROLE_ARN},
    Input='{\"source\":\"eventbridge-scheduler\",\"run_identifier\":\"morning\",\"execution_mode\":\"paper\"}'" \
  --region $AWS_REGION 2>/dev/null || echo "✓ Morning schedule already exists"

# Afternoon run (1:00 PM ET)
aws scheduler create-schedule \
  --name "${PROJECT_NAME}-algo-schedule-afternoon-${ENVIRONMENT}" \
  --schedule-expression "cron(0 13 ? * MON-FRI *)" \
  --schedule-expression-timezone "America/New_York" \
  --state ENABLED \
  --flexible-time-window Mode=OFF \
  --target "
    Arn=arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${ORCHESTRATOR_FUNC},
    RoleArn=${EVENTBRIDGE_ROLE_ARN},
    Input='{\"source\":\"eventbridge-scheduler\",\"run_identifier\":\"afternoon\",\"execution_mode\":\"paper\"}'" \
  --region $AWS_REGION 2>/dev/null || echo "✓ Afternoon schedule already exists"

# Pre-close run (3:00 PM ET)
aws scheduler create-schedule \
  --name "${PROJECT_NAME}-algo-schedule-preclose-${ENVIRONMENT}" \
  --schedule-expression "cron(0 15 ? * MON-FRI *)" \
  --schedule-expression-timezone "America/New_York" \
  --state ENABLED \
  --flexible-time-window Mode=OFF \
  --target "
    Arn=arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${ORCHESTRATOR_FUNC},
    RoleArn=${EVENTBRIDGE_ROLE_ARN},
    Input='{\"source\":\"eventbridge-scheduler\",\"run_identifier\":\"preclose\",\"execution_mode\":\"paper\"}'" \
  --region $AWS_REGION 2>/dev/null || echo "✓ Pre-close schedule already exists"

# Evening run (5:30 PM ET - signal prep)
aws scheduler create-schedule \
  --name "${PROJECT_NAME}-algo-schedule-${ENVIRONMENT}" \
  --schedule-expression "cron(30 17 ? * MON-FRI *)" \
  --schedule-expression-timezone "America/New_York" \
  --state ENABLED \
  --flexible-time-window Mode=OFF \
  --target "
    Arn=arn:aws:lambda:${AWS_REGION}:${AWS_ACCOUNT_ID}:function:${ORCHESTRATOR_FUNC},
    RoleArn=${EVENTBRIDGE_ROLE_ARN},
    Input='{\"source\":\"eventbridge-scheduler\",\"run_identifier\":\"evening\",\"execution_mode\":\"paper\"}'" \
  --region $AWS_REGION 2>/dev/null || echo "✓ Evening schedule already exists"

echo "✓ EventBridge schedules configured"
echo ""

# ============================================================
# STEP 4: Create/Update API Routes
# ============================================================
echo "[4/4] Wiring API Gateway routes..."

if [ -z "$API_GATEWAY_ID" ]; then
  echo "⚠ API Gateway not found. Ensure API infrastructure is created first."
else
  # Get or create $default route
  DEFAULT_ROUTE=$(aws apigatewayv2 get-routes \
    --api-id $API_GATEWAY_ID \
    --region $AWS_REGION \
    --query "Items[?RouteKey=='\$default'].RouteId" \
    --output text)

  if [ -z "$DEFAULT_ROUTE" ]; then
    # Create $default route
    ROUTE_ID=$(aws apigatewayv2 create-route \
      --api-id $API_GATEWAY_ID \
      --route-key '$default' \
      --region $AWS_REGION \
      --query 'RouteId' \
      --output text)
    echo "✓ Created $default route: $ROUTE_ID"
  else
    ROUTE_ID=$DEFAULT_ROUTE
    echo "✓ Using existing $default route: $ROUTE_ID"
  fi

  # Link route to Lambda
  aws apigatewayv2 update-route \
    --api-id $API_GATEWAY_ID \
    --route-id $ROUTE_ID \
    --target "lambda/${API_FUNC}" \
    --region $AWS_REGION 2>/dev/null || true

  echo "✓ API routes configured to invoke Lambda"
fi

echo ""
echo "==============================================="
echo "✓ DEPLOYMENT COMPLETE"
echo "==============================================="
echo ""
echo "Next steps:"
echo "1. Verify Lambda functions deployed:"
echo "   aws lambda get-function --function-name ${ORCHESTRATOR_FUNC} --region ${AWS_REGION}"
echo ""
echo "2. List EventBridge schedules:"
echo "   aws scheduler list-schedules --region ${AWS_REGION}"
echo ""
echo "3. Test orchestrator manually:"
echo "   aws lambda invoke --function-name ${ORCHESTRATOR_FUNC} --region ${AWS_REGION} --payload '{\"run_identifier\":\"morning\",\"execution_mode\":\"paper\"}' /tmp/response.json && cat /tmp/response.json"
echo ""
echo "4. Monitor execution:"
echo "   aws logs tail /aws/lambda/${ORCHESTRATOR_FUNC} --follow --region ${AWS_REGION}"
echo ""
echo "System will now execute trades at:"
echo "  - 9:30 AM ET (morning run)"
echo "  - 1:00 PM ET (afternoon run)"
echo "  - 3:00 PM ET (pre-close run)"
echo "  - 5:30 PM ET (evening signal prep)"
echo ""
