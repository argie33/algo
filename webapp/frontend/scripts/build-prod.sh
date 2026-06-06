#!/bin/bash
# Production build wrapper that ensures all environment variables are passed
# to setup-prod.js and Vite with proper error handling

set -e

echo "🔨 Starting production build..."

# Extract environment variables with fallbacks
API_URL="${VITE_API_URL:-}"
ENVIRONMENT="${VITE_ENVIRONMENT:-production}"
USER_POOL_ID="${VITE_COGNITO_USER_POOL_ID:-}"
CLIENT_ID="${VITE_COGNITO_CLIENT_ID:-}"
COGNITO_DOMAIN="${VITE_COGNITO_DOMAIN:-}"
CLOUDFRONT_URL="${VITE_CLOUDFRONT_DOMAIN:-}"

# Validate critical variables before build
if [ -z "$API_URL" ]; then
  echo "⚠️  WARNING: VITE_API_URL is empty - frontend may not reach API"
fi

if [ -z "$USER_POOL_ID" ] && [ -z "$CLIENT_ID" ]; then
  echo "⚠️  WARNING: Cognito credentials not set - authentication will be disabled"
fi

# Run setup-prod.js EXPLICITLY with all arguments
# Arguments: apiUrl, environment, userPoolId, clientId, cognitoDomain, cloudfrontUrl
echo "📝 Running setup-prod.js with API_URL=$API_URL"
node scripts/setup-prod.js "$API_URL" "$ENVIRONMENT" "$USER_POOL_ID" "$CLIENT_ID" "$COGNITO_DOMAIN" "$CLOUDFRONT_URL"

if [ $? -ne 0 ]; then
  echo "❌ ERROR: setup-prod.js failed"
  exit 1
fi

# Verify config.js was created
if [ ! -f "public/config.js" ]; then
  echo "❌ ERROR: config.js not created in public/"
  exit 1
fi

echo "✓ config.js created successfully"
cat public/config.js
echo ""

# Run build with Vite
echo "📦 Running Vite build..."
export VITE_API_URL="$API_URL"
export VITE_ENVIRONMENT="$ENVIRONMENT"
export VITE_COGNITO_USER_POOL_ID="$USER_POOL_ID"
export VITE_COGNITO_CLIENT_ID="$CLIENT_ID"

vite build

# Verify dist/config.js exists (Vite should have copied it from public/)
if [ ! -f "dist/config.js" ]; then
  echo "❌ ERROR: config.js not found in dist/ after Vite build"
  exit 1
fi

echo "✓ Build completed successfully"
echo "✓ config.js in dist/: $(cat dist/config.js | head -1)"
