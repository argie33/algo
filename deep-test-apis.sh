#!/bin/bash
echo "DEEP API INSPECTION - CHECKING ACTUAL DATA AND ERRORS"
echo "========================================================"
echo ""

test_api_detailed() {
  local url=$1
  local name=$2
  echo "Testing: $name"
  echo "URL: $url"
  response=$(curl -s "$url" 2>&1)
  echo "Response:"
  echo "$response" | head -300
  echo ""
  echo "---"
  echo ""
}

test_api_detailed "http://localhost:3001/api/stocks?limit=2" "STOCKS"
test_api_detailed "http://localhost:3001/api/signals/stocks?timeframe=daily&limit=2" "SIGNALS DAILY"
test_api_detailed "http://localhost:3001/api/price/history/AAPL?timeframe=daily&limit=2" "PRICE HISTORY"
test_api_detailed "http://localhost:3001/api/financials/AAPL/balance-sheet?period=annual" "FINANCIALS BALANCE SHEET"
test_api_detailed "http://localhost:3001/api/sectors/sectors?limit=2" "SECTORS"

