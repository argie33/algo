#!/bin/bash
# Post-Deployment Verification Script
# Run this after GitHub Actions deployment completes to verify all components

set -e
REGION=${AWS_REGION:-us-east-1}
PROJECT=${PROJECT_NAME:-algo}
ENV=${ENVIRONMENT:-dev}

echo "=== POST-DEPLOYMENT VERIFICATION ==="
echo "Project: $PROJECT"
echo "Environment: $ENV"
echo "Region: $REGION"
echo ""

# ──────────────────────────────────────────────────────────────────
# 1. RDS Connectivity Check
# ──────────────────────────────────────────────────────────────────
echo "1️⃣  Checking RDS Database..."

RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "${PROJECT}-postgres-${ENV}" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$RDS_ENDPOINT" ] || [ "$RDS_ENDPOINT" = "None" ]; then
  echo "❌ RDS endpoint not found"
  exit 1
fi

echo "✅ RDS Endpoint: $RDS_ENDPOINT"

# ──────────────────────────────────────────────────────────────────
# 2. Frontend S3 Bucket Check
# ──────────────────────────────────────────────────────────────────
echo ""
echo "2️⃣  Checking Frontend S3 Bucket..."

BUCKET=$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name, '${PROJECT}-frontend')].Name | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$BUCKET" ] || [ "$BUCKET" = "None" ]; then
  echo "❌ Frontend bucket not found"
  exit 1
fi

echo "✅ Frontend Bucket: s3://${BUCKET}"

# ──────────────────────────────────────────────────────────────────
# 3. API Gateway Check
# ──────────────────────────────────────────────────────────────────
echo ""
echo "3️⃣  Checking API Gateway..."

API_ID=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='${PROJECT}-api-${ENV}'].ApiId | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$API_ID" ] || [ "$API_ID" = "None" ]; then
  echo "❌ API Gateway not found"
  exit 1
fi

API_ENDPOINT=$(aws apigatewayv2 get-apis \
  --query "Items[?Name=='${PROJECT}-api-${ENV}'].ApiEndpoint | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

echo "✅ API Gateway: $API_ENDPOINT"

# ──────────────────────────────────────────────────────────────────
# 4. ECS Cluster Check
# ──────────────────────────────────────────────────────────────────
echo ""
echo "4️⃣  Checking ECS Cluster..."

CLUSTER=$(aws ecs list-clusters \
  --query "clusterArns[?contains(@, '${PROJECT}')][0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$CLUSTER" ] || [ "$CLUSTER" = "None" ]; then
  echo "❌ ECS cluster not found"
  exit 1
fi

CLUSTER_NAME=$(basename "$CLUSTER")
echo "✅ ECS Cluster: $CLUSTER_NAME"

# ──────────────────────────────────────────────────────────────────
# 5. CloudFront Distribution Check
# ──────────────────────────────────────────────────────────────────
echo ""
echo "5️⃣  Checking CloudFront Distribution..."

CF_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Enabled==\`true\`].Id | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$CF_ID" ] || [ "$CF_ID" = "None" ]; then
  echo "❌ CloudFront distribution not found"
  exit 1
fi

CF_DOMAIN=$(aws cloudfront get-distribution \
  --id "$CF_ID" \
  --query 'Distribution.DomainName' \
  --output text --region $REGION 2>/dev/null || echo "")

echo "✅ CloudFront: https://${CF_DOMAIN}"

# ──────────────────────────────────────────────────────────────────
# 6. Lambda Functions Check
# ──────────────────────────────────────────────────────────────────
echo ""
echo "6️⃣  Checking Lambda Functions..."

API_FUNC=$(aws lambda list-functions \
  --query "Functions[?Name=='${PROJECT}-api-${ENV}'].FunctionArn | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$API_FUNC" ] || [ "$API_FUNC" = "None" ]; then
  echo "❌ API Lambda not found"
  exit 1
fi

echo "✅ API Lambda: ${PROJECT}-api-${ENV}"

ALGO_FUNC=$(aws lambda list-functions \
  --query "Functions[?Name=='${PROJECT}-algo-${ENV}'].FunctionArn | [0]" \
  --output text --region $REGION 2>/dev/null || echo "")

if [ -z "$ALGO_FUNC" ] || [ "$ALGO_FUNC" = "None" ]; then
  echo "❌ Algo Lambda not found"
  exit 1
fi

echo "✅ Algo Lambda: ${PROJECT}-algo-${ENV}"

# ──────────────────────────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────────────────────────
echo ""
echo "=== ✅ ALL INFRASTRUCTURE VERIFIED ==="
echo ""
echo "Next steps:"
echo "  1. Set environment variables:"
echo "     export DB_HOST=$RDS_ENDPOINT"
echo "     export DB_PORT=5432"
echo "     export DB_USER=postgres"
echo "     export DB_PASSWORD=<your_password>"
echo "     export DB_NAME=stocks"
echo ""
echo "  2. Verify database connectivity:"
echo "     python3 verify_rds_connectivity.py"
echo ""
echo "  3. Run loaders:"
echo "     python3 run-all-loaders.py"
echo ""
echo "  4. Test orchestrator:"
echo "     python3 algo/algo_orchestrator.py --mode paper --dry-run"
