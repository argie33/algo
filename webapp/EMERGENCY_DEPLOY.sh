#!/bin/bash
set -e

echo "🚨 EMERGENCY LAMBDA DEPLOYMENT 🚨"
echo "=================================="
echo ""

# Check if admin profile exists
if ! aws sts get-caller-identity --profile admin &>/dev/null; then
    echo "❌ ERROR: AWS 'admin' profile not configured"
    echo ""
    echo "Please configure admin credentials first:"
    echo "  aws configure --profile admin"
    echo ""
    exit 1
fi

echo "✅ Admin credentials verified"
IDENTITY=$(aws sts get-caller-identity --profile admin --query 'Arn' --output text)
echo "   Deploying as: $IDENTITY"
echo ""

# Navigate to lambda directory
cd /home/stocks/algo/webapp/lambda || { echo "❌ Lambda directory not found"; exit 1; }

echo "📦 Creating deployment package..."
# Create clean deployment package
rm -f ../lambda-deploy.zip
zip -q -r ../lambda-deploy.zip . \
    -x "*.git*" \
    -x "*node_modules/*" \
    -x "*.log" \
    -x "*__pycache__*" \
    -x "*.pyc" \
    -x "test*" \
    -x "*.md"

echo "✅ Package created: $(du -h ../lambda-deploy.zip | cut -f1)"
echo ""

echo "🚀 Deploying to Lambda..."
aws lambda update-function-code \
    --function-name stocks-webapp-api-dev \
    --zip-file fileb://../lambda-deploy.zip \
    --profile admin \
    --region us-east-1

echo ""
echo "⏳ Waiting for deployment to complete..."
aws lambda wait function-updated \
    --function-name stocks-webapp-api-dev \
    --profile admin \
    --region us-east-1

echo ""
echo "🧪 Testing endpoint..."
sleep 5  # Give it a moment to warm up

if curl -s -f -m 10 https://qda42av7je.execute-api.us-east-1.amazonaws.com/dev/api/health > /tmp/health-check.json 2>&1; then
    echo "✅ Health check PASSED"
    cat /tmp/health-check.json | jq . 2>/dev/null || cat /tmp/health-check.json
else
    echo "⚠️ Health check still failing, checking logs..."
    aws logs tail /aws/lambda/stocks-webapp-api-dev --profile admin --since 1m --format short | tail -20
fi

echo ""
echo "=================================="
echo "Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Test the site: https://d1copuy2oqlazx.cloudfront.net"
echo "2. Check Lambda logs if issues persist:"
echo "   aws logs tail /aws/lambda/stocks-webapp-api-dev --profile admin --follow"
echo ""
