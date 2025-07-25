#!/bin/bash

# CloudFront API Routing Fix Script
# Fixes the core issue: /api/* routes returning HTML instead of JSON

set -e

echo "🔧 CloudFront API Routing Fix"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Find the CloudFront distribution
echo -e "${BLUE}Step 1: Finding CloudFront distribution...${NC}"

DISTRIBUTION_ID=$(aws cloudfront list-distributions \
  --query 'DistributionList.Items[?contains(Aliases.Items, `d1zb7knau41vl9.cloudfront.net`)].Id' \
  --output text 2>/dev/null || echo "")

if [ -z "$DISTRIBUTION_ID" ]; then
  echo -e "${RED}❌ Could not find CloudFront distribution for d1zb7knau41vl9.cloudfront.net${NC}"
  echo "Trying alternative search methods..."
  
  # Try searching by domain in origins
  DISTRIBUTION_ID=$(aws cloudfront list-distributions \
    --query 'DistributionList.Items[?contains(to_string(Origins.Items[*].DomainName), `d1zb7knau41vl9`)].Id' \
    --output text 2>/dev/null || echo "")
fi

if [ -z "$DISTRIBUTION_ID" ]; then
  echo -e "${RED}❌ CloudFront distribution not found. Please provide it manually:${NC}"
  echo "1. Go to AWS CloudFront Console"
  echo "2. Find distribution serving d1zb7knau41vl9.cloudfront.net"
  echo "3. Copy the Distribution ID (starts with E)"
  echo "4. Run: export DISTRIBUTION_ID=YOUR_ID_HERE"
  echo "5. Re-run this script"
  exit 1
fi

echo -e "${GREEN}✅ Found CloudFront Distribution: ${DISTRIBUTION_ID}${NC}"

# Step 2: Get current distribution configuration
echo -e "${BLUE}Step 2: Getting current distribution configuration...${NC}"

aws cloudfront get-distribution-config --id "$DISTRIBUTION_ID" --output json > current-config.json

if [ ! -f current-config.json ]; then
  echo -e "${RED}❌ Failed to get distribution configuration${NC}"
  exit 1
fi

# Extract ETag for updates
ETAG=$(jq -r '.ETag' current-config.json)
echo -e "${GREEN}✅ Current ETag: ${ETAG}${NC}"

# Step 3: Analyze current configuration
echo -e "${BLUE}Step 3: Analyzing current behaviors...${NC}"

BEHAVIORS=$(jq '.DistributionConfig.CacheBehaviors.Items[]? | select(.PathPattern == "/api/*")' current-config.json)

if [ -n "$BEHAVIORS" ]; then
  echo -e "${YELLOW}⚠️  /api/* behavior already exists - will update it${NC}"
else
  echo -e "${YELLOW}⚠️  No /api/* behavior found - will create new one${NC}"
fi

# Step 4: Find Lambda/API Gateway origin
echo -e "${BLUE}Step 4: Finding Lambda/API Gateway origin...${NC}"

# Look for non-S3 origins (Lambda Function URLs or API Gateway)
LAMBDA_ORIGIN=$(jq -r '.DistributionConfig.Origins.Items[] | select(.DomainName | contains("lambda") or contains("execute-api") or contains("amazonaws")) | .Id' current-config.json | head -1)

if [ -z "$LAMBDA_ORIGIN" ]; then
  echo -e "${RED}❌ No Lambda/API Gateway origin found${NC}"
  echo "Available origins:"
  jq -r '.DistributionConfig.Origins.Items[] | "\(.Id): \(.DomainName)"' current-config.json
  echo ""
  echo -e "${YELLOW}Please add a Lambda Function URL or API Gateway origin first:${NC}"
  echo "1. Go to CloudFront Console"
  echo "2. Edit Distribution"
  echo "3. Add Origin with Lambda Function URL or API Gateway domain"
  echo "4. Re-run this script"
  exit 1
fi

echo -e "${GREEN}✅ Found Lambda/API origin: ${LAMBDA_ORIGIN}${NC}"

# Step 5: Create new configuration
echo -e "${BLUE}Step 5: Creating updated configuration...${NC}"

# Create the API behavior configuration
API_BEHAVIOR=$(cat <<EOF
{
  "PathPattern": "/api/*",
  "TargetOriginId": "$LAMBDA_ORIGIN",
  "ViewerProtocolPolicy": "redirect-to-https",
  "AllowedMethods": {
    "Quantity": 7,
    "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
    "CachedMethods": {
      "Quantity": 2,
      "Items": ["GET", "HEAD"]
    }
  },
  "ForwardedValues": {
    "QueryString": true,
    "Cookies": {
      "Forward": "all"
    },
    "Headers": {
      "Quantity": 4,
      "Items": ["Authorization", "Content-Type", "Accept", "Origin"]
    }
  },
  "TrustedSigners": {
    "Enabled": false,
    "Quantity": 0
  },
  "MinTTL": 0,
  "DefaultTTL": 0,
  "MaxTTL": 0,
  "Compress": false
}
EOF
)

# Update the distribution configuration
jq --argjson new_behavior "$API_BEHAVIOR" '
  .DistributionConfig.CacheBehaviors.Items |= (
    # Remove existing /api/* behavior if it exists
    map(select(.PathPattern != "/api/*")) +
    # Add new behavior at the beginning (highest precedence)
    [$new_behavior]
  ) |
  .DistributionConfig.CacheBehaviors.Quantity = (.DistributionConfig.CacheBehaviors.Items | length)
' current-config.json > updated-config.json

# Remove ETag from config for update
jq 'del(.ETag)' updated-config.json > final-config.json

echo -e "${GREEN}✅ Configuration updated${NC}"

# Step 6: Deploy the changes
echo -e "${BLUE}Step 6: Deploying CloudFront changes...${NC}"

aws cloudfront update-distribution \
  --id "$DISTRIBUTION_ID" \
  --distribution-config file://final-config.json \
  --if-match "$ETAG" \
  --output json > deployment-result.json

if [ $? -eq 0 ]; then
  echo -e "${GREEN}✅ CloudFront update initiated successfully!${NC}"
  
  # Get deployment status
  DEPLOYMENT_STATUS=$(jq -r '.Distribution.Status' deployment-result.json)
  echo -e "${YELLOW}📡 Deployment Status: ${DEPLOYMENT_STATUS}${NC}"
  
  if [ "$DEPLOYMENT_STATUS" = "InProgress" ]; then
    echo -e "${YELLOW}⏳ Distribution is updating... This typically takes 5-15 minutes${NC}"
    echo -e "${BLUE}💡 You can monitor progress in the CloudFront Console${NC}"
  fi
else
  echo -e "${RED}❌ Failed to update CloudFront distribution${NC}"
  exit 1
fi

# Step 7: Provide testing instructions
echo ""
echo -e "${BLUE}🧪 TESTING INSTRUCTIONS${NC}"
echo "================================"
echo "1. Wait 5-15 minutes for propagation"
echo "2. Test API endpoint:"
echo -e "   ${YELLOW}curl -H 'Accept: application/json' https://d1zb7knau41vl9.cloudfront.net/api/health${NC}"
echo "3. Expected result: JSON response (not HTML)"
echo "4. Run comprehensive test:"
echo -e "   ${YELLOW}node test-api-routing.js${NC}"
echo ""
echo -e "${GREEN}🎯 Once complete, all pages should display live data!${NC}"

# Cleanup
rm -f current-config.json updated-config.json final-config.json deployment-result.json

echo -e "${GREEN}✅ CloudFront fix script completed!${NC}"