#!/bin/bash

echo "🧪 API DATA INTEGRITY TEST"
echo "================================"

BASE_URL="http://localhost:5001"

# Test 1: Sectors endpoint
echo ""
echo "▶ Test 1: GET /api/market/sectors"
curl -s "$BASE_URL/api/market/sectors" 2>&1 | head -20

# Test 2: Seasonality (presidential cycle data)
echo ""
echo ""
echo "▶ Test 2: GET /api/market/seasonality"
curl -s "$BASE_URL/api/market/seasonality" 2>&1 | jq '.data | length' 2>/dev/null || echo "Check jq output"

# Test 3: Stock scores
echo ""
echo "▶ Test 3: GET /api/stocks/scores?limit=5"
curl -s "$BASE_URL/api/stocks/scores?limit=5" 2>&1 | head -15

# Test 4: Health check
echo ""
echo "▶ Test 4: GET /health"
curl -s "$BASE_URL/health" 2>&1

# Test 5: Dashboard data
echo ""
echo "▶ Test 5: GET /api/dashboard"
curl -s "$BASE_URL/api/dashboard" 2>&1 | head -20

echo ""
echo "================================"
echo "✅ API tests completed"
