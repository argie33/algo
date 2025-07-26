#!/bin/bash

# CloudFront API Routing Fix Script
# Automatically configures CloudFront behaviors to route /api/* to Lambda instead of S3

set -e

echo "🚀 CloudFront API Routing Fix Script"
echo "===================================="

# Configuration
DISTRIBUTION_DOMAIN="d1zb7knau41vl9.cloudfront.net"
API_GATEWAY_DOMAIN="2m14opj30h.execute-api.us-east-1.amazonaws.com"
STAGE="dev"

echo "📋 Configuration:"
echo "  Distribution: $DISTRIBUTION_DOMAIN"
echo "  API Gateway: $API_GATEWAY_DOMAIN"
echo "  Stage: $STAGE"
echo ""

# Get CloudFront distribution ID
echo "🔍 Finding CloudFront distribution ID..."
DISTRIBUTION_ID=$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Aliases.Items[0]=='$DISTRIBUTION_DOMAIN'].Id" \
  --output text 2>/dev/null || echo "")

if [ -z "$DISTRIBUTION_ID" ]; then
  echo "❌ Error: Could not find CloudFront distribution for $DISTRIBUTION_DOMAIN"
  echo "   Please check:"
  echo "   1. AWS CLI is configured correctly"
  echo "   2. Distribution domain is correct"
  echo "   3. You have CloudFront permissions"
  exit 1
fi

echo "✅ Found distribution ID: $DISTRIBUTION_ID"

# Get current distribution config
echo "📥 Getting current distribution configuration..."
aws cloudfront get-distribution-config --id "$DISTRIBUTION_ID" > /tmp/cloudfront-config.json

if [ ! -f /tmp/cloudfront-config.json ]; then
  echo "❌ Error: Failed to get distribution configuration"
  exit 1
fi

# Extract ETag for updates
ETAG=$(jq -r '.ETag' /tmp/cloudfront-config.json)
echo "✅ Configuration ETag: $ETAG"

# Create the API behavior configuration
echo "🔧 Creating API behavior configuration..."

# Check if API behavior already exists
API_BEHAVIOR_EXISTS=$(jq -r '.DistributionConfig.CacheBehaviors.Items[]? | select(.PathPattern == "/api/*") | .PathPattern' /tmp/cloudfront-config.json || echo "")

if [ "$API_BEHAVIOR_EXISTS" == "/api/*" ]; then
  echo "⚠️  API behavior already exists. Updating existing behavior..."
  
  # Update existing behavior
  jq '.DistributionConfig.CacheBehaviors.Items |= map(
    if .PathPattern == "/api/*" then
      . + {
        "TargetOriginId": "api-gateway",
        "ViewerProtocolPolicy": "redirect-to-https",
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        "OriginRequestPolicyId": "88a5eaf4-2fd4-4709-b370-b4c650ea3fcf",
        "ResponseHeadersPolicyId": "67f7725c-6f97-4210-82d7-5512b31e9d03",
        "AllowedMethods": {
          "Quantity": 7,
          "Items": ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
          "CachedMethods": {
            "Quantity": 2,
            "Items": ["GET", "HEAD"]
          }
        },
        "Compress": true,
        "SmoothStreaming": false
      }
    else
      .
    end
  )' /tmp/cloudfront-config.json > /tmp/cloudfront-config-updated.json

else
  echo "➕ Creating new API behavior..."
  
  # Add new API behavior
  jq '.DistributionConfig.CacheBehaviors.Quantity += 1 |
    .DistributionConfig.CacheBehaviors.Items += [{
      "PathPattern": "/api/*",
      "TargetOriginId": "api-gateway",
      "ViewerProtocolPolicy": "redirect-to-https",
      "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
      "OriginRequestPolicyId": "88a5eaf4-2fd4-4709-b370-b4c650ea3fcf", 
      "ResponseHeadersPolicyId": "67f7725c-6f97-4210-82d7-5512b31e9d03",
      "AllowedMethods": {
        "Quantity": 7,
        "Items": ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
        "CachedMethods": {
          "Quantity": 2,
          "Items": ["GET", "HEAD"]
        }
      },
      "Compress": true,
      "SmoothStreaming": false,
      "FieldLevelEncryptionId": "",
      "RealtimeLogConfigArn": "",
      "TrustedSigners": {
        "Enabled": false,
        "Quantity": 0,
        "Items": []
      },
      "TrustedKeyGroups": {
        "Enabled": false,
        "Quantity": 0,
        "Items": []
      },
      "FunctionAssociations": {
        "Quantity": 0,
        "Items": []
      },
      "LambdaFunctionAssociations": {
        "Quantity": 0,
        "Items": []
      }
    }]' /tmp/cloudfront-config.json > /tmp/cloudfront-config-updated.json
fi

# Check if API Gateway origin exists
API_ORIGIN_EXISTS=$(jq -r '.DistributionConfig.Origins.Items[]? | select(.Id == "api-gateway") | .Id' /tmp/cloudfront-config-updated.json || echo "")

if [ "$API_ORIGIN_EXISTS" != "api-gateway" ]; then
  echo "➕ Adding API Gateway origin..."
  
  # Add API Gateway origin
  jq '.DistributionConfig.Origins.Quantity += 1 |
    .DistributionConfig.Origins.Items += [{
      "Id": "api-gateway",
      "DomainName": "'$API_GATEWAY_DOMAIN'",
      "OriginPath": "/'$STAGE'",
      "CustomOriginConfig": {
        "HTTPPort": 80,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "https-only",
        "OriginSslProtocols": {
          "Quantity": 1,
          "Items": ["TLSv1.2"]
        },
        "OriginReadTimeout": 30,
        "OriginKeepaliveTimeout": 5
      },
      "ConnectionAttempts": 3,
      "ConnectionTimeout": 10,
      "OriginShield": {
        "Enabled": false
      }
    }]' /tmp/cloudfront-config-updated.json > /tmp/cloudfront-config-final.json
else
  echo "✅ API Gateway origin already exists"
  cp /tmp/cloudfront-config-updated.json /tmp/cloudfront-config-final.json
fi

# Extract just the DistributionConfig for the update
jq '.DistributionConfig' /tmp/cloudfront-config-final.json > /tmp/distribution-config-only.json

echo "📤 Updating CloudFront distribution..."

# Update the distribution
aws cloudfront update-distribution \
  --id "$DISTRIBUTION_ID" \
  --distribution-config file:///tmp/distribution-config-only.json \
  --if-match "$ETAG" > /tmp/update-result.json

if [ $? -eq 0 ]; then
  echo "✅ CloudFront distribution updated successfully!"
  
  NEW_ETAG=$(jq -r '.ETag' /tmp/update-result.json)
  echo "   New ETag: $NEW_ETAG"
  
  echo ""
  echo "🕐 Distribution is now updating..."
  echo "   Propagation time: 5-15 minutes"
  echo ""
  echo "🧪 Test commands (run after 15 minutes):"
  echo "   curl -H \"Accept: application/json\" https://$DISTRIBUTION_DOMAIN/api/health"
  echo "   node test-api-routing.js"
  echo ""
  echo "✨ All API endpoints should now return JSON instead of HTML!"
  
else
  echo "❌ Failed to update CloudFront distribution"
  echo "   Check AWS CLI permissions and try again"
  exit 1
fi

# Cleanup temporary files
rm -f /tmp/cloudfront-config*.json /tmp/distribution-config-only.json /tmp/update-result.json

echo "🎉 CloudFront API routing fix completed!"