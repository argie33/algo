#!/bin/bash
# Test AWS mode after Terraform deployment

set -e

echo "=========================================="
echo "Testing AWS Mode Fix"
echo "=========================================="

API_URL="https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
TEST_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJpc3MiOiJ0ZXN0In0.test"

echo ""
echo "1. Testing API Gateway connectivity..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -I "$API_URL/api/algo/positions")
echo "   Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ API Gateway REACHABLE"
else
    echo "   ❌ API Gateway returned $HTTP_CODE (expected 200)"
    exit 1
fi

echo ""
echo "2. Testing positions endpoint..."
curl -s "$API_URL/api/algo/positions" \
    -H "Authorization: Bearer $TEST_TOKEN" | head -100

echo ""
echo "3. Testing trades endpoint..."
curl -s "$API_URL/api/algo/trades" \
    -H "Authorization: Bearer $TEST_TOKEN" | head -50

echo ""
echo "4. Testing scores endpoint..."
curl -s "$API_URL/api/algo/scores" \
    -H "Authorization: Bearer $TEST_TOKEN" | head -50

echo ""
echo "=========================================="
echo "Testing complete!"
echo "=========================================="
