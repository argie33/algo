#!/bin/bash

echo "📊 COMPREHENSIVE API TEST"
echo "======================="
echo ""

test_endpoint() {
  local path=$1
  local name=$2
  
  local start=$(date +%s%N)
  local response=$(curl -s -w "\n%{http_code}" "http://localhost:3001$path" 2>&1)
  local end=$(date +%s%N)
  local time=$(( ($end - $start) / 1000000 ))
  
  local http_code=$(echo "$response" | tail -1)
  local body=$(echo "$response" | head -1)
  
  if [ "$http_code" == "200" ]; then
    local items=$(echo "$body" | grep -o '"items":\[\|"data":{' | head -1)
    if echo "$body" | grep -q '"success":true'; then
      echo "✅ $name (${time}ms)"
    else
      echo "⚠️  $name - success=false (${time}ms)"
    fi
  else
    echo "❌ $name - HTTP $http_code (${time}ms)"
  fi
}

test_endpoint "/api/health?quick=true" "Health (quick)"
test_endpoint "/api/sectors/sectors" "Sectors"
test_endpoint "/api/industries/industries" "Industries"
test_endpoint "/api/stocks?limit=10" "Stocks"
test_endpoint "/api/market/sentiment?range=30d" "Market Sentiment"
test_endpoint "/api/market/top-movers" "Top Movers"
test_endpoint "/api/stocks/search?q=AAPL" "Stock Search"

echo ""
echo "✅ API TEST COMPLETE"
