#!/bin/bash
# Post-deployment verification - check if API can now connect to RDS

API_ENDPOINT="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api"

echo "========== POST-DEPLOYMENT VERIFICATION =========="
echo "Deployment Date: $(date)"
echo ""

echo "1. Checking API health..."
health=$(curl -s "$API_ENDPOINT/health" 2>&1)
if echo "$health" | grep -q "healthy"; then
  echo "✅ API health: OK"
else
  echo "⚠️ API response: $health"
fi
echo ""

echo "2. Testing RDS connectivity via API..."
echo "   Testing /api/scores/stockscores endpoint..."
response=$(curl -s "$API_ENDPOINT/scores/stockscores?limit=1" 2>&1)

if echo "$response" | grep -q "error"; then
  echo "⚠️ Still getting error:"
  echo "$response" | head -100
else
  echo "✅ API responded successfully"
  echo "Response: $response" | head -50
fi
echo ""

echo "3. Once data is available..."
echo "   - Test /api/market/indices for market data"
echo "   - Test /api/economic for economic data"
echo "   - Refresh frontend in CloudFront browser"
echo ""

echo "Verification complete!"
