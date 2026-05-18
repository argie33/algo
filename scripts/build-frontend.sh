#!/bin/bash
# Build and deploy frontend to AWS
# Usage: ./scripts/build-frontend.sh <API_URL> [S3_BUCKET] [DISTRIBUTION_ID]

set -e

API_URL="${1:-}"
S3_BUCKET="${2:-algo-frontend-dev}"
DISTRIBUTION_ID="${3:-}"

if [ -z "$API_URL" ]; then
  echo "❌ API_URL required"
  echo "Usage: $0 <API_URL> [S3_BUCKET] [DIST_ID]"
  echo ""
  echo "Get API_URL from AWS:"
  echo "  aws apigatewayv2 get-apis --region us-east-1 --query \"Items[?Name=='algo-api-dev'].ApiEndpoint\" --output text"
  exit 1
fi

echo "🔨 Building frontend with API_URL=$API_URL"
cd "$(dirname "$0")/../webapp/frontend"

export VITE_API_URL="$API_URL"
npm ci
npm run build

echo "✅ Frontend built at dist/"

if [ -z "$S3_BUCKET" ]; then
  echo "⏭️  Skipping S3 deploy (no bucket specified)"
  echo "   To deploy: aws s3 sync dist/ s3://$S3_BUCKET/ --delete"
  exit 0
fi

echo "📤 Uploading to S3: s3://$S3_BUCKET"
aws s3 sync dist/ "s3://$S3_BUCKET/" --delete --region us-east-1

if [ -n "$DISTRIBUTION_ID" ]; then
  echo "🔄 Invalidating CloudFront: $DISTRIBUTION_ID"
  aws cloudfront create-invalidation \
    --distribution-id "$DISTRIBUTION_ID" \
    --paths "/*" \
    --region us-east-1
  echo "✅ CloudFront invalidated"
fi

echo ""
echo "✅ FRONTEND DEPLOYED"
echo "   Frontend: https://$S3_BUCKET.s3.amazonaws.com/ (or CloudFront if configured)"
echo "   API: $API_URL"
