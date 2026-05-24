#!/bin/bash
# Post-Deployment Live Verification
# Run this script after infrastructure deployment completes successfully

set -e

echo "=========================================="
echo "AWS Deployment Verification"
echo "=========================================="
echo ""

# Get deployment outputs
echo "Step 1: Retrieving deployment outputs from Terraform..."
cd terraform

API_GATEWAY=$(terraform output -raw api_gateway_endpoint 2>/dev/null || echo "")
CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain 2>/dev/null || echo "")
RDS_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null || echo "")

if [ -z "$API_GATEWAY" ] || [ -z "$CLOUDFRONT_DOMAIN" ]; then
  echo "❌ ERROR: Could not retrieve deployment outputs"
  echo "   - API Gateway: $API_GATEWAY"
  echo "   - CloudFront: $CLOUDFRONT_DOMAIN"
  exit 1
fi

echo "✅ Deployment outputs retrieved:"
echo "   - API Gateway: $API_GATEWAY"
echo "   - CloudFront: $CLOUDFRONT_DOMAIN"
echo "   - RDS: $RDS_ENDPOINT"
echo ""

# Test API endpoints
echo "Step 2: Testing API endpoints..."
endpoints=(
  "api/algo/status"
  "api/algo/trades"
  "api/prices?limit=5"
  "api/signals?limit=10"
)

success_count=0
for endpoint in "${endpoints[@]}"; do
  response=$(curl -s -w "\n%{http_code}" "$API_GATEWAY/$endpoint" 2>&1)
  http_code=$(echo "$response" | tail -n1)

  if [ "$http_code" = "200" ]; then
    echo "  ✅ GET /$endpoint - $http_code OK"
    ((success_count++))
  else
    echo "  ❌ GET /$endpoint - $http_code FAILED"
  fi
done

if [ "$success_count" -lt 2 ]; then
  echo ""
  echo "❌ WARNING: API endpoints not responding. This may be expected if:"
  echo "   - Database not yet initialized"
  echo "   - Loaders haven't run yet (they run at 3:25-5:30 AM ET)"
  echo "   - Cold start in progress"
  echo ""
  echo "Monitor CloudWatch logs: https://console.aws.amazon.com/cloudwatch/"
fi

echo ""

# Test frontend
echo "Step 3: Testing frontend deployment..."
response=$(curl -s -w "\n%{http_code}" "https://$CLOUDFRONT_DOMAIN/" 2>&1)
http_code=$(echo "$response" | tail -n1)

if [ "$http_code" = "200" ]; then
  echo "  ✅ CloudFront frontend accessible"
  echo "  URL: https://$CLOUDFRONT_DOMAIN/"
else
  echo "  ❌ CloudFront not responding ($http_code)"
  echo "  This may be normal if deployment just completed (cache warm-up in progress)"
fi

echo ""
echo "=========================================="
echo "Deployment Verification Complete"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Monitor loaders in EventBridge: https://console.aws.amazon.com/events/"
echo "2. Check data in RDS: Query price_daily, technical_data_daily tables"
echo "3. Monitor API Lambda: https://console.aws.amazon.com/lambda/"
echo "4. Test live trading: Manually invoke test-orchestrator.yml"
echo "5. Verify portfolio: Check algo_portfolio_snapshots table"
echo ""
echo "Dashboards:"
echo "  - API: $API_GATEWAY"
echo "  - Frontend: https://$CLOUDFRONT_DOMAIN/"
echo "  - AWS: https://console.aws.amazon.com/"
echo ""
