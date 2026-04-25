#!/bin/bash

echo "=================================================="
echo " COMPREHENSIVE API ENDPOINT TEST"
echo " Testing all data display endpoints"
echo "=================================================="
echo ""

test_endpoint() {
  local name=$1
  local url=$2
  local status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:3001$url")
  local result=$(curl -s "http://localhost:3001$url" | head -c 200)
  
  if [ "$status" = "200" ]; then
    echo "✅ $name ($status): Data returned"
  else
    echo "❌ $name ($status): $(echo $result | head -c 100)"
  fi
}

echo "STOCK DATA:"
test_endpoint "Stocks list" "/api/stocks?limit=5"
test_endpoint "Stock details" "/api/stocks/AAPL"
test_endpoint "Stock scores" "/api/scores?limit=5"

echo ""
echo "FINANCIAL DATA:"
test_endpoint "Balance sheet" "/api/financials/AAPL/balance-sheet?period=annual"
test_endpoint "Income statement" "/api/financials/AAPL/income-statement?period=annual"
test_endpoint "Cash flow" "/api/financials/AAPL/cash-flow?period=annual"

echo ""
echo "MARKET DATA:"
test_endpoint "Sectors" "/api/sectors"
test_endpoint "Industries" "/api/industries"
test_endpoint "Price history" "/api/price/history/AAPL?timeframe=daily&limit=5"

echo ""
echo "TECHNICAL & SENTIMENT:"
test_endpoint "Technicals" "/api/technicals/daily?symbol=AAPL&limit=5"
test_endpoint "Sentiment" "/api/sentiment/data?limit=5"
test_endpoint "Earnings history" "/api/earnings/info?symbol=AAPL"
test_endpoint "Analyst sentiment" "/api/sentiment/data?limit=5"

echo ""
echo "TRADING SIGNALS & STRATEGIES:"
test_endpoint "Buy/Sell signals" "/api/signals/stocks?timeframe=daily&limit=5"
test_endpoint "Covered calls" "/api/strategies/covered-calls?limit=5"

echo ""
echo "=================================================="
echo "ALL TESTS COMPLETE"
echo "=================================================="
